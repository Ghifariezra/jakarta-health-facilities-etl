# core/http_client.py
import aiohttp
import asyncio
from core.singleton import BaseSingleton


class AsyncHTTPClient(BaseSingleton):
    """
    Klien HTTP Asinkron dengan:
    - Semaphore untuk membatasi konkurensi (hindari rate limit)
    - Retry logic dengan exponential backoff
    - Timeout yang dapat dikonfigurasi
    """

    def __init__(
        self,
        timeout_seconds: int = 30,
        max_concurrent: int = 10,  # Batasi request paralel
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ):
        self.timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        print(
            f"[AsyncHTTPClient] Siap — max_concurrent={max_concurrent}, "
            f"max_retries={max_retries}, timeout={timeout_seconds}s"
        )

    async def post_json(
        self,
        session: aiohttp.ClientSession,
        url: str,
        payload: dict,
        task_id: int = 1,
        total_tasks: int = 1,
    ) -> dict | None:
        """
        POST request tunggal dengan retry + exponential backoff.
        Semaphore memastikan tidak lebih dari `max_concurrent` request
        berjalan bersamaan di satu waktu.
        """
        # Gunakan semaphore untuk membatasi konkurensi
        async with self.semaphore:
            for attempt in range(1, self.max_retries + 1):
                try:
                    async with session.post(
                        url, json=payload, timeout=self.timeout
                    ) as response:

                        if response.status == 200:
                            print(
                                f"[Task {task_id}/{total_tasks}] ✅ Berhasil "
                                f"(attempt {attempt})"
                            )
                            return await response.json()

                        # Jangan retry untuk error client (4xx), kecuali 429 (rate limit)
                        if response.status == 429:
                            wait = self.retry_delay * (2 ** (attempt - 1))
                            print(
                                f"[Task {task_id}/{total_tasks}] ⚠️ Rate limited "
                                f"(429), tunggu {wait:.1f}s..."
                            )
                            await asyncio.sleep(wait)
                            continue

                        if 400 <= response.status < 500:
                            print(
                                f"[Task {task_id}/{total_tasks}] ❌ Client error "
                                f"({response.status}), tidak di-retry."
                            )
                            return None

                        # Server error (5xx) — retry
                        print(
                            f"[Task {task_id}/{total_tasks}] ⚠️ Server error "
                            f"({response.status}), attempt {attempt}/{self.max_retries}"
                        )

                except asyncio.TimeoutError:
                    print(
                        f"[Task {task_id}/{total_tasks}] ⏳ Timeout "
                        f"(attempt {attempt}/{self.max_retries})"
                    )
                except aiohttp.ClientConnectionError as e:
                    print(
                        f"[Task {task_id}/{total_tasks}] 🔌 Koneksi gagal: {e} "
                        f"(attempt {attempt}/{self.max_retries})"
                    )
                except Exception as e:
                    print(
                        f"[Task {task_id}/{total_tasks}] ❌ Error tak terduga: {e}"
                    )
                    return None  # Jangan retry untuk error yang tidak dikenal

                # Exponential backoff sebelum retry berikutnya
                if attempt < self.max_retries:
                    wait = self.retry_delay * (2 ** (attempt - 1))
                    await asyncio.sleep(wait)

            print(
                f"[Task {task_id}/{total_tasks}] 💀 Menyerah setelah "
                f"{self.max_retries} percobaan."
            )
            return None

    async def fetch_all_post(self, url: str, payloads: list[dict]) -> list:
        """
        Eksekusi semua POST request secara paralel (dibatasi semaphore).
        Menggunakan return_exceptions=True agar satu gagal tidak
        membatalkan yang lain.
        """
        total_tasks = len(payloads)

        # Satu session untuk semua request — lebih efisien (connection pooling)
        connector = aiohttp.TCPConnector(limit=total_tasks)
        async with aiohttp.ClientSession(connector=connector) as session:
            tasks = [
                self.post_json(session, url, payload, idx, total_tasks)
                for idx, payload in enumerate(payloads, start=1)
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        # Tangani jika ada exception yang lolos dari gather
        sanitized = []
        for i, result in enumerate(results, start=1):
            if isinstance(result, BaseException):
                print(
                    f"[Task {i}] ⚠️ Exception tertangkap dari gather: {result}")
                sanitized.append(None)
            else:
                sanitized.append(result)

        return sanitized
