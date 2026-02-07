"""
Streaming Response Optimizer

Optimize TTFB and overall performance of streaming requests.
"""

import asyncio
import aiohttp
from typing import AsyncIterator, Optional
from collections import deque

from timem.utils.logging import get_logger

logger = get_logger(__name__)


class StreamingOptimizer:
    """Streaming response optimizer"""
    
    def __init__(
        self,
        buffer_size: int = 1024,
        chunk_size: int = 128,
        connect_timeout: float = 3.0,
        read_timeout: float = 5.0
    ):
        """
        Initialize streaming optimizer
        
        Args:
            buffer_size: Buffer size (bytes)
            chunk_size: Chunk size per read (bytes)
            connect_timeout: Connection timeout (seconds)
            read_timeout: Read timeout (seconds)
        """
        self.buffer_size = buffer_size
        self.chunk_size = chunk_size
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout
        
        logger.info(
            f"Streaming optimizer initialized: buffer={buffer_size}B, "
            f"chunk={chunk_size}B, "
            f"connect_timeout={connect_timeout}s, "
            f"read_timeout={read_timeout}s"
        )
    
    async def optimized_stream(
        self,
        session: aiohttp.ClientSession,
        url: str,
        json: dict,
        headers: dict,
        **kwargs
    ) -> AsyncIterator[str]:
        """
        Optimized streaming request
        
        Args:
            session: aiohttp session
            url: Request URL
            json: Request JSON data
            headers: Request headers
            **kwargs: Other parameters
            
        Yields:
            Streaming response chunks
        """
        # Create optimized timeout configuration
        timeout = aiohttp.ClientTimeout(
            connect=self.connect_timeout,
            sock_read=self.read_timeout,
            total=None  # Streaming requests have no total timeout
        )
        
        async with session.post(
            url,
            json=json,
            headers=headers,
            timeout=timeout,
            **kwargs
        ) as response:
            
            if response.status != 200:
                error_text = await response.text()
                raise aiohttp.ClientResponseError(
                    request_info=response.request_info,
                    history=response.history,
                    status=response.status,
                    message=f"Streaming API error: {error_text}"
                )
            
            # Use buffer to optimize reading
            buffer = []
            buffer_bytes = 0
            
            # Small chunk reads for better responsiveness
            async for chunk_bytes in response.content.iter_chunked(self.chunk_size):
                try:
                    chunk = chunk_bytes.decode('utf-8', errors='ignore')
                    
                    # Add to buffer
                    buffer.append(chunk)
                    buffer_bytes += len(chunk)
                    
                    # Buffer reaches threshold or encounters complete message
                    if buffer_bytes >= self.buffer_size or '\n' in chunk:
                        # Output buffer content
                        yield ''.join(buffer)
                        buffer = []
                        buffer_bytes = 0
                        
                except UnicodeDecodeError as e:
                    logger.warning(f"Streaming decode error: {e}")
                    continue
            
            # Output remaining buffer
            if buffer:
                yield ''.join(buffer)
    
    async def stream_with_backpressure(
        self,
        session: aiohttp.ClientSession,
        url: str,
        json: dict,
        headers: dict,
        max_buffer: int = 10,
        **kwargs
    ) -> AsyncIterator[str]:
        """
        Streaming request with backpressure control
        
        Args:
            session: aiohttp session
            url: Request URL
            json: Request JSON data
            headers: Request headers
            max_buffer: Maximum buffer count
            **kwargs: Other parameters
            
        Yields:
            Streaming response chunks
        """
        queue = asyncio.Queue(maxsize=max_buffer)
        exception_holder = []
        
        async def producer():
            """Producer: read data from network"""
            try:
                async for chunk in self.optimized_stream(
                    session, url, json, headers, **kwargs
                ):
                    await queue.put(chunk)
            except Exception as e:
                exception_holder.append(e)
            finally:
                await queue.put(None)  # End marker
        
        # Start producer
        producer_task = asyncio.create_task(producer())
        
        try:
            # Consumer: read data from queue
            while True:
                chunk = await queue.get()
                
                if chunk is None:  # End marker
                    break
                
                yield chunk
                
                # Check if there's an exception
                if exception_holder:
                    raise exception_holder[0]
        
        finally:
            # Clean up producer task
            if not producer_task.done():
                producer_task.cancel()
                try:
                    await producer_task
                except asyncio.CancelledError:
                    pass
    
    def create_optimized_connector(self) -> aiohttp.TCPConnector:
        """
        Create optimized TCP connector
        
        Returns:
            Optimized TCPConnector
        """
        return aiohttp.TCPConnector(
            limit_per_host=50,  # Streaming connections can be more
            force_close=False,   # Keep connections
            enable_cleanup_closed=False,  # Don't force cleanup
            keepalive_timeout=120.0,  # Streaming connections keep longer
            ttl_dns_cache=300  # DNS cache 5 minutes
        )
    
    def create_ssl_context(self):
        """
        Create SSL context with HTTP/2 support
        
        Returns:
            SSL context
        """
        import ssl
        
        ssl_context = ssl.create_default_context()
        
        # Support HTTP/2
        try:
            ssl_context.set_alpn_protocols(['h2', 'http/1.1'])
            logger.debug("SSL context supports HTTP/2")
        except AttributeError:
            # Python version doesn't support ALPN
            logger.debug("SSL context doesn't support HTTP/2")
        
        ssl_context.check_hostname = True
        ssl_context.verify_mode = ssl.CERT_REQUIRED
        
        return ssl_context


# Global streaming optimizer (singleton)
_global_streaming_optimizer: Optional[StreamingOptimizer] = None


def get_global_streaming_optimizer() -> StreamingOptimizer:
    """Get global streaming optimizer"""
    global _global_streaming_optimizer
    
    if _global_streaming_optimizer is None:
        from timem.utils.config_manager import get_llm_config
        
        llm_config = get_llm_config()
        streaming_config = llm_config.get("resilience", {}).get("streaming", {})
        
        _global_streaming_optimizer = StreamingOptimizer(
            buffer_size=streaming_config.get("buffer_size", 1024),
            chunk_size=streaming_config.get("chunk_size", 128),
            connect_timeout=streaming_config.get("connect_timeout", 3.0),
            read_timeout=streaming_config.get("read_timeout", 5.0),
        )
        
        logger.info("Global streaming optimizer initialized")
    
    return _global_streaming_optimizer

