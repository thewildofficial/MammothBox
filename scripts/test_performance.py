"""
Performance testing script for File Allocator API.

Tests:
- Load testing (100 concurrent uploads)
- Search performance under load
- Database performance benchmarks
"""

import asyncio
import time
import statistics
from typing import List, Dict, Any
import httpx
import json
from pathlib import Path
import io
from PIL import Image

# Configuration
BASE_URL = "http://localhost:8000"
CONCURRENT_REQUESTS = 100
TEST_DURATION_SECONDS = 60


class PerformanceTester:
    """Performance testing utility."""

    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url
        self.results: Dict[str, List[float]] = {
            "ingest_latency": [],
            "search_latency": [],
            "job_processing_latency": []
        }

    async def test_ingest_performance(self, num_requests: int = 100):
        """
        Test ingest endpoint performance.

        Args:
            num_requests: Number of concurrent requests
        """
        print(
            f"\n=== Testing Ingest Performance ({num_requests} requests) ===")

        async with httpx.AsyncClient(timeout=30.0) as client:
            tasks = []
            for i in range(num_requests):
                task = self._ingest_request(client, i)
                tasks.append(task)

            start_time = time.time()
            results = await asyncio.gather(*tasks, return_exceptions=True)
            total_time = time.time() - start_time

        # Analyze results
        successes = [r for r in results if not isinstance(r, Exception)]
        failures = [r for r in results if isinstance(r, Exception)]

        print(f"\nResults:")
        print(f"  Total requests: {num_requests}")
        print(f"  Successful: {len(successes)}")
        print(f"  Failed: {len(failures)}")
        print(f"  Total time: {total_time:.2f}s")
        print(f"  Throughput: {num_requests / total_time:.2f} req/s")

        if self.results["ingest_latency"]:
            latencies = self.results["ingest_latency"]
            print(f"\nLatency Statistics:")
            print(f"  Mean: {statistics.mean(latencies):.3f}s")
            print(f"  Median: {statistics.median(latencies):.3f}s")
            print(f"  P95: {statistics.quantiles(latencies, n=20)[18]:.3f}s")
            print(f"  P99: {statistics.quantiles(latencies, n=100)[98]:.3f}s")
            print(f"  Min: {min(latencies):.3f}s")
            print(f"  Max: {max(latencies):.3f}s")

        # Check performance targets
        if latencies:
            p95 = statistics.quantiles(latencies, n=20)[18]
            target = 0.2  # 200ms
            status = "✅ PASS" if p95 < target else "❌ FAIL"
            print(f"\nPerformance Target: P95 < {target}s")
            print(f"Actual P95: {p95:.3f}s {status}")

    async def _ingest_request(self, client: httpx.AsyncClient, request_id: int) -> Dict:
        """Make a single ingest request."""
        # Create test image
        image = Image.new('RGB', (100, 100), color=(
            request_id % 256, 100, 150))
        img_bytes = io.BytesIO()
        image.save(img_bytes, format='JPEG')
        img_bytes.seek(0)

        files = {
            'files': (f'test_image_{request_id}.jpg', img_bytes, 'image/jpeg')
        }
        data = {
            'request_id': f'perf_test_{request_id}'
        }

        start_time = time.time()
        try:
            response = await client.post(
                f"{self.base_url}/api/v1/ingest/media",
                files=files,
                data=data
            )
            latency = time.time() - start_time
            self.results["ingest_latency"].append(latency)

            return {
                "status": response.status_code,
                "latency": latency,
                "success": response.status_code == 200
            }
        except Exception as e:
            return {"error": str(e), "success": False}

    async def test_search_performance(self, num_requests: int = 100):
        """
        Test search endpoint performance.

        Args:
            num_requests: Number of concurrent search requests
        """
        print(
            f"\n=== Testing Search Performance ({num_requests} requests) ===")

        # First, ensure we have some data
        print("Seeding data for search tests...")
        await self._seed_test_data(10)

        async with httpx.AsyncClient(timeout=30.0) as client:
            tasks = []
            for i in range(num_requests):
                task = self._search_request(client, i)
                tasks.append(task)

            start_time = time.time()
            results = await asyncio.gather(*tasks, return_exceptions=True)
            total_time = time.time() - start_time

        # Analyze results
        successes = [r for r in results if not isinstance(
            r, Exception) and r.get("success")]
        failures = [r for r in results if isinstance(
            r, Exception) or not r.get("success")]

        print(f"\nResults:")
        print(f"  Total requests: {num_requests}")
        print(f"  Successful: {len(successes)}")
        print(f"  Failed: {len(failures)}")
        print(f"  Total time: {total_time:.2f}s")
        print(f"  Throughput: {num_requests / total_time:.2f} req/s")

        if self.results["search_latency"]:
            latencies = self.results["search_latency"]
            print(f"\nLatency Statistics:")
            print(f"  Mean: {statistics.mean(latencies):.3f}s")
            print(f"  Median: {statistics.median(latencies):.3f}s")
            print(f"  P95: {statistics.quantiles(latencies, n=20)[18]:.3f}s")
            print(f"  P99: {statistics.quantiles(latencies, n=100)[98]:.3f}s")

            # Check performance target
            p95 = statistics.quantiles(latencies, n=20)[18]
            target = 0.15  # 150ms
            status = "✅ PASS" if p95 < target else "❌ FAIL"
            print(f"\nPerformance Target: P95 < {target}s")
            print(f"Actual P95: {p95:.3f}s {status}")

    async def _search_request(self, client: httpx.AsyncClient, request_id: int) -> Dict:
        """Make a single search request."""
        queries = [
            "beautiful sunset",
            "city skyline",
            "mountain landscape",
            "ocean waves",
            "forest trees"
        ]
        query = queries[request_id % len(queries)]

        start_time = time.time()
        try:
            response = await client.post(
                f"{self.base_url}/api/v1/search/media",
                json={"query": query, "limit": 10}
            )
            latency = time.time() - start_time
            self.results["search_latency"].append(latency)

            return {
                "status": response.status_code,
                "latency": latency,
                "success": response.status_code == 200
            }
        except Exception as e:
            return {"error": str(e), "success": False}

    async def _seed_test_data(self, count: int):
        """Seed test data for search tests."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            for i in range(count):
                image = Image.new('RGB', (100, 100), color=(i * 25, 100, 150))
                img_bytes = io.BytesIO()
                image.save(img_bytes, format='JPEG')
                img_bytes.seek(0)

                files = {
                    'files': (f'seed_image_{i}.jpg', img_bytes, 'image/jpeg')
                }
                data = {'request_id': f'seed_{i}'}

                try:
                    await client.post(
                        f"{self.base_url}/api/v1/ingest/media",
                        files=files,
                        data=data
                    )
                except Exception:
                    pass  # Ignore errors during seeding

    async def test_sustained_load(self, duration_seconds: int = 60):
        """
        Test sustained load over time.

        Args:
            duration_seconds: Duration of test in seconds
        """
        print(f"\n=== Testing Sustained Load ({duration_seconds}s) ===")

        start_time = time.time()
        request_count = 0
        errors = 0

        async with httpx.AsyncClient(timeout=30.0) as client:
            while time.time() - start_time < duration_seconds:
                try:
                    await self._ingest_request(client, request_count)
                    request_count += 1
                except Exception:
                    errors += 1

                # Small delay to simulate realistic load
                await asyncio.sleep(0.1)

        total_time = time.time() - start_time
        throughput = request_count / total_time

        print(f"\nResults:")
        print(f"  Duration: {total_time:.2f}s")
        print(f"  Total requests: {request_count}")
        print(f"  Errors: {errors}")
        print(f"  Error rate: {(errors / request_count * 100):.2f}%")
        print(f"  Average throughput: {throughput:.2f} req/s")

    def print_summary(self):
        """Print summary of all tests."""
        print("\n" + "=" * 70)
        print("PERFORMANCE TEST SUMMARY")
        print("=" * 70)

        # Ingest performance
        if self.results["ingest_latency"]:
            latencies = self.results["ingest_latency"]
            p95 = statistics.quantiles(latencies, n=20)[18]
            target_met = "✅" if p95 < 0.2 else "❌"
            print(f"\nIngest Performance:")
            print(f"  P95 Latency: {p95:.3f}s (target: < 0.2s) {target_met}")
            print(f"  Total requests: {len(latencies)}")

        # Search performance
        if self.results["search_latency"]:
            latencies = self.results["search_latency"]
            p95 = statistics.quantiles(latencies, n=20)[18]
            target_met = "✅" if p95 < 0.15 else "❌"
            print(f"\nSearch Performance:")
            print(f"  P95 Latency: {p95:.3f}s (target: < 0.15s) {target_met}")
            print(f"  Total requests: {len(latencies)}")

        print("\n" + "=" * 70)


async def main():
    """Run performance tests."""
    tester = PerformanceTester()

    # Test 1: Concurrent ingest
    await tester.test_ingest_performance(num_requests=CONCURRENT_REQUESTS)

    # Wait for processing
    print("\nWaiting for jobs to process...")
    await asyncio.sleep(10)

    # Test 2: Search performance
    await tester.test_search_performance(num_requests=50)

    # Test 3: Sustained load (optional, comment out for quick tests)
    # await tester.test_sustained_load(duration_seconds=30)

    # Print summary
    tester.print_summary()


if __name__ == "__main__":
    print("Starting Performance Tests...")
    print(f"Target: {BASE_URL}")
    print(f"Concurrent Requests: {CONCURRENT_REQUESTS}")

    asyncio.run(main())
