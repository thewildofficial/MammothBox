"""
Worker supervisor for managing background job processing.

Manages worker threads, preloads shared resources (ML models),
and executes job processors with retry logic and crash recovery.
"""

import logging
import threading
import time
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Dict, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from src.catalog.database import get_db_session
from src.catalog.models import Job
from src.queue.interface import QueueBackend, QueueMessage

logger = logging.getLogger(__name__)


class JobProcessor(ABC):
    """Abstract base class for job processors."""
    
    @abstractmethod
    def process(self, job_data: dict, db: Session) -> Dict[str, any]:
        """
        Process a job.
        
        Args:
            job_data: Job payload data
            db: Database session
            
        Returns:
            Dictionary with processing results
            
        Raises:
            Exception: If processing fails
        """
        pass


class WorkerSupervisor:
    """
    Supervisor for managing worker threads and job processing.
    
    Spawns N worker threads (configurable), polls queue for jobs,
    routes to appropriate processors, and handles retries/errors.
    """
    
    def __init__(
        self,
        queue_backend: QueueBackend,
        processors: Dict[str, JobProcessor],
        num_workers: int = 4
    ):
        """
        Initialize worker supervisor.
        
        Args:
            queue_backend: Queue backend to poll for jobs
            processors: Dictionary mapping job_type -> processor
            num_workers: Number of worker threads to spawn
        """
        self.queue = queue_backend
        self.processors = processors
        self.num_workers = num_workers
        self.workers: list[threading.Thread] = []
        self.running = False
        self._shutdown_event = threading.Event()
        self._model_cache: Dict[str, any] = {}  # For preloaded ML models
    
    def start(self) -> None:
        """Start worker threads."""
        if self.running:
            logger.warning("Worker supervisor already running")
            return
        
        self.running = True
        self._shutdown_event.clear()
        
        logger.info(f"Starting {self.num_workers} worker threads")
        
        # Preload shared resources (ML models, etc.)
        self._preload_resources()
        
        # Start worker threads
        for i in range(self.num_workers):
            worker = threading.Thread(
                target=self._worker_loop,
                name=f"Worker-{i+1}",
                daemon=True
            )
            worker.start()
            self.workers.append(worker)
        
        logger.info("Worker supervisor started")
    
    def stop(self, timeout: float = 30.0) -> None:
        """
        Stop worker threads gracefully.
        
        Args:
            timeout: Maximum time to wait for workers to finish
        """
        if not self.running:
            return
        
        logger.info("Stopping worker supervisor...")
        self.running = False
        self._shutdown_event.set()
        
        # Wait for workers to finish
        for worker in self.workers:
            worker.join(timeout=timeout / len(self.workers))
            if worker.is_alive():
                logger.warning(f"Worker {worker.name} did not stop gracefully")
        
        self.workers.clear()
        logger.info("Worker supervisor stopped")
    
    def _preload_resources(self) -> None:
        """Preload shared resources like ML models."""
        logger.info("Preloading shared resources...")
        
        # Preload CLIP model for media processing
        try:
            from src.media.embedder import MediaEmbedder
            embedder = MediaEmbedder()
            # Trigger model loading
            embedder._load_model()
            self._model_cache['clip_embedder'] = embedder
            logger.info("CLIP model preloaded successfully")
        except Exception as e:
            logger.warning(f"Failed to preload CLIP model: {e}")
            logger.warning("CLIP model will be loaded lazily on first use")
        
        logger.info("Shared resources preloaded")
    
    def _worker_loop(self) -> None:
        """Main worker loop - polls queue and processes jobs."""
        worker_name = threading.current_thread().name
        logger.info(f"{worker_name} started")
        
        while self.running:
            try:
                # Poll queue with timeout
                message = self.queue.dequeue(timeout=1.0)
                
                if message is None:
                    # No jobs available, continue polling
                    continue
                
                # Process job
                self._process_job(message, worker_name)
                
            except Exception as e:
                logger.error(f"{worker_name} error in worker loop: {e}", exc_info=True)
                # Continue running despite errors
                time.sleep(1)
        
        logger.info(f"{worker_name} stopped")
    
    def _process_job(self, message: QueueMessage, worker_name: str) -> None:
        """
        Process a single job.
        
        Args:
            message: Queue message to process
            worker_name: Name of worker thread processing this job
        """
        job_id = message.job_id
        logger.info(f"{worker_name} processing job {job_id} (type: {message.job_type})")
        
        # Use a single database session for the entire job processing operation
        # to avoid race conditions and ensure data consistency
        with get_db_session() as db:
            job = db.query(Job).filter(Job.id == job_id).first()
            if not job:
                logger.error(f"Job {job_id} not found in database")
                self.queue.ack(job_id)
                return
            
            # Update status to processing
            job.status = "processing"
            job.started_at = datetime.utcnow()
            db.commit()
            
            try:
                # Get processor for this job type
                processor = self.processors.get(message.job_type)
                if not processor:
                    raise ValueError(f"No processor registered for job type: {message.job_type}")
                
                # Process job (using the same session)
                result = processor.process(message.job_data, db)
                
                # Re-query job after processing (processor may have committed, detaching the object)
                job = db.query(Job).filter(Job.id == job_id).first()
                if not job:
                    logger.error(f"Job {job_id} not found after processing")
                    self.queue.ack(job_id)
                    return
                
                # Update job status to done
                job.status = "done"
                job.completed_at = datetime.utcnow()
                db.commit()
                
                # Acknowledge job
                self.queue.ack(job_id)
                logger.info(f"{worker_name} completed job {job_id}")
                
            except Exception as e:
                error_msg = str(e)
                logger.error(f"{worker_name} failed to process job {job_id}: {error_msg}", exc_info=True)
                
                # Re-query job from database to ensure we have latest state
                # (refresh doesn't work if job was created in a different session)
                job = db.query(Job).filter(Job.id == job_id).first()
                if not job:
                    logger.error(f"Job {job_id} not found in database during error handling")
                    self.queue.nack(job_id, error_msg)
                    return
                
                job.error_message = error_msg
                
                # Negative acknowledge (queue will increment retry_count and handle retry logic)
                self.queue.nack(job_id, error_msg)
                
                # After nack, sync the queue's incremented retry_count back to database
                # The queue increments message.retry_count, so we use that value
                job.retry_count = message.retry_count
                
                # Check if max retries exceeded (using the queue's incremented value)
                if job.retry_count >= job.max_retries:
                    job.status = "failed"
                    job.dead_letter = True
                    job.completed_at = datetime.utcnow()
                else:
                    # Schedule retry with exponential backoff
                    # Use retry_count - 1 for backoff since queue already incremented it
                    backoff_seconds = 2 ** (job.retry_count - 1)
                    job.next_retry_at = datetime.utcnow() + timedelta(seconds=backoff_seconds)
                    job.status = "queued"
                
                db.commit()

