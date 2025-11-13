"""
Redis queue backend implementation.

Provides distributed queue support using Redis for scaling across multiple instances.
"""

import json
import time
from datetime import datetime, timedelta
from typing import Optional, Dict
from uuid import UUID

import redis
from redis.exceptions import ConnectionError as RedisConnectionError

from src.queue.interface import QueueBackend, QueueMessage


class RedisQueue(QueueBackend):
    """
    Redis-backed queue backend.
    
    Uses Redis lists for queue operations and Redis hashes for job metadata.
    Supports distributed workers across multiple instances.
    """
    
    # Redis key prefixes
    QUEUE_KEY = "queue:jobs"
    PROCESSING_KEY = "queue:processing"
    DLQ_KEY = "queue:dlq"
    JOB_META_KEY = "queue:meta"
    
    def __init__(self, redis_url: str = "redis://localhost:6379/0", max_retries: int = 3):
        """
        Initialize Redis queue backend.
        
        Args:
            redis_url: Redis connection URL
            max_retries: Maximum retry attempts before moving to DLQ
        """
        self.redis_url = redis_url
        self.max_retries = max_retries
        self._client: Optional[redis.Redis] = None
        self._closed = False
        
        # Parse Redis URL
        try:
            from urllib.parse import urlparse
            parsed = urlparse(redis_url)
            self._host = parsed.hostname or "localhost"
            self._port = parsed.port or 6379
            self._db = int(parsed.path.lstrip('/')) if parsed.path else 0
        except Exception as e:
            raise ValueError(f"Invalid Redis URL: {redis_url}") from e
    
    def _get_client(self) -> redis.Redis:
        """Get or create Redis client."""
        if self._client is None:
            try:
                self._client = redis.Redis(
                    host=self._host,
                    port=self._port,
                    db=self._db,
                    decode_responses=False,  # We'll handle encoding ourselves
                    socket_connect_timeout=5
                )
                # Test connection
                self._client.ping()
            except RedisConnectionError as e:
                raise ConnectionError(f"Failed to connect to Redis at {self._host}:{self._port}: {e}")
        return self._client
    
    def enqueue(self, message: QueueMessage) -> None:
        """Add a job to the queue."""
        if self._closed:
            raise RuntimeError("Queue is closed")
        
        client = self._get_client()
        
        # Serialize message
        job_data = {
            "job_id": str(message.job_id),
            "job_type": message.job_type,
            "job_data": message.job_data,
            "priority": message.priority,
            "retry_count": message.retry_count,
            "max_retries": message.max_retries,
            "created_at": message.created_at.isoformat() if message.created_at else None,
            "next_retry_at": message.next_retry_at.isoformat() if message.next_retry_at else None
        }
        
        job_json = json.dumps(job_data).encode('utf-8')
        
        # Store job metadata
        client.hset(
            f"{self.JOB_META_KEY}:{message.job_id}",
            mapping={
                "data": job_json,
                "created_at": message.created_at.isoformat() if message.created_at else datetime.utcnow().isoformat()
            }
        )
        
        # Add to queue with priority (use sorted set for priority ordering)
        # Score = -priority (negative so higher priority = lower score = dequeued first)
        client.zadd(
            self.QUEUE_KEY,
            {str(message.job_id): -message.priority}
        )
    
    def dequeue(self, timeout: Optional[float] = None) -> Optional[QueueMessage]:
        """
        Get the next job from the queue.
        
        Uses blocking pop from sorted set, respecting retry delays.
        """
        if self._closed:
            return None
        
        client = self._get_client()
        deadline = time.time() + timeout if timeout else None
        
        while True:
            # Check timeout
            if deadline and time.time() >= deadline:
                return None
            
            # Get next job (lowest score = highest priority)
            # Check if any job is ready (not delayed)
            now = datetime.utcnow()
            
            # Get all jobs, check retry times
            jobs = client.zrange(self.QUEUE_KEY, 0, -1, withscores=True)
            
            for job_id_bytes, score in jobs:
                job_id_str = job_id_bytes.decode('utf-8')
                job_id = UUID(job_id_str)
                
                # Get job metadata
                meta = client.hgetall(f"{self.JOB_META_KEY}:{job_id_str}")
                if not meta:
                    continue
                
                job_data = json.loads(meta[b'data'].decode('utf-8'))
                
                # Check retry delay
                if job_data.get('next_retry_at'):
                    retry_at = datetime.fromisoformat(job_data['next_retry_at'])
                    if retry_at > now:
                        continue  # Not ready yet
                
                # Remove from queue and add to processing
                if client.zrem(self.QUEUE_KEY, job_id_str):
                    client.hset(f"{self.PROCESSING_KEY}:{job_id_str}", "started_at", datetime.utcnow().isoformat())
                    
                    # Reconstruct message
                    return QueueMessage(
                        job_id=job_id,
                        job_type=job_data['job_type'],
                        job_data=job_data['job_data'],
                        priority=int(score) if score else 0,
                        retry_count=job_data.get('retry_count', 0),
                        max_retries=job_data.get('max_retries', self.max_retries),
                        created_at=datetime.fromisoformat(job_data['created_at']) if job_data.get('created_at') else datetime.utcnow(),
                        next_retry_at=datetime.fromisoformat(job_data['next_retry_at']) if job_data.get('next_retry_at') else None
                    )
            
            # No ready jobs, wait a bit
            if timeout:
                remaining = deadline - time.time()
                if remaining <= 0:
                    return None
                time.sleep(min(0.1, remaining))
            else:
                time.sleep(0.1)
    
    def ack(self, job_id: UUID) -> None:
        """Acknowledge successful job completion."""
        client = self._get_client()
        job_id_str = str(job_id)
        
        # Remove from processing
        client.delete(f"{self.PROCESSING_KEY}:{job_id_str}")
        # Optionally remove metadata (or keep for audit)
        # client.delete(f"{self.JOB_META_KEY}:{job_id_str}")
    
    def nack(self, job_id: UUID, error: str) -> None:
        """
        Handle job failure with retry logic.
        
        If retry count < max_retries, schedules retry with exponential backoff.
        Otherwise, moves to dead-letter queue.
        """
        client = self._get_client()
        job_id_str = str(job_id)
        
        # Get job metadata
        meta = client.hgetall(f"{self.JOB_META_KEY}:{job_id_str}")
        if not meta:
            return
        
        job_data = json.loads(meta[b'data'].decode('utf-8'))
        retry_count = job_data.get('retry_count', 0)
        max_retries = job_data.get('max_retries', self.max_retries)
        
        # Remove from processing
        client.delete(f"{self.PROCESSING_KEY}:{job_id_str}")
        
        # Check if we should retry
        if retry_count < max_retries:
            # Exponential backoff
            backoff_seconds = 2 ** retry_count
            next_retry_at = datetime.utcnow() + timedelta(seconds=backoff_seconds)
            
            # Update job data
            job_data['retry_count'] = retry_count + 1
            job_data['next_retry_at'] = next_retry_at.isoformat()
            job_data['last_error'] = error
            
            # Update metadata
            client.hset(
                f"{self.JOB_META_KEY}:{job_id_str}",
                "data",
                json.dumps(job_data).encode('utf-8')
            )
            
            # Re-enqueue
            client.zadd(
                self.QUEUE_KEY,
                {job_id_str: -job_data.get('priority', 0)}
            )
        else:
            # Move to dead-letter queue
            job_data['dead_letter'] = True
            job_data['final_error'] = error
            job_data['failed_at'] = datetime.utcnow().isoformat()
            
            client.hset(
                f"{self.DLQ_KEY}:{job_id_str}",
                mapping={
                    "data": json.dumps(job_data).encode('utf-8'),
                    "failed_at": datetime.utcnow().isoformat()
                }
            )
    
    def size(self) -> int:
        """Get current queue size."""
        client = self._get_client()
        return client.zcard(self.QUEUE_KEY)
    
    def get_dlq_size(self) -> int:
        """Get dead-letter queue size."""
        client = self._get_client()
        # Count DLQ keys
        return len(client.keys(f"{self.DLQ_KEY}:*"))
    
    def close(self) -> None:
        """Close the queue backend."""
        self._closed = True
        if self._client:
            self._client.close()
            self._client = None
