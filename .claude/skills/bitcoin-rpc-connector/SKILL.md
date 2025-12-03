---
name: bitcoin-rpc-connector
description: Auto-generate Bitcoin Core RPC connection code with cookie auth, bitcoin.conf parsing, OS path detection, and error handling. 60% token savings (2,500→1,000).
---

# Bitcoin RPC Connector

Generate standardized Bitcoin Core RPC connection code with automatic authentication, path detection, and resilient error handling.

## Quick Start

**User says**: "Create Bitcoin RPC connection with cookie auth"

**Skill generates**:
```python
import json
import os
import platform
from pathlib import Path
from typing import Optional
from urllib.request import Request, urlopen
from urllib.error import URLError

class BitcoinRPC:
    """Bitcoin Core RPC connection manager"""

    def __init__(
        self,
        data_dir: Optional[Path] = None,
        rpc_url: str = "http://127.0.0.1:8332",
        timeout: int = 30
    ):
        self.data_dir = data_dir or self._detect_data_dir()
        self.rpc_url = rpc_url
        self.timeout = timeout
        self._rpc_user, self._rpc_password = self._get_credentials()

    def _detect_data_dir(self) -> Path:
        """Auto-detect Bitcoin data directory based on OS"""
        system = platform.system()

        if system == "Linux":
            return Path.home() / ".bitcoin"
        elif system == "Darwin":  # macOS
            return Path.home() / "Library" / "Application Support" / "Bitcoin"
        elif system == "Windows":
            return Path(os.environ.get("APPDATA", "")) / "Bitcoin"
        else:
            raise OSError(f"Unsupported OS: {system}")

    def _get_credentials(self) -> tuple[str, str]:
        """Get RPC credentials from .cookie or bitcoin.conf"""
        # Try cookie authentication first (Bitcoin Core default)
        cookie_file = self.data_dir / ".cookie"
        if cookie_file.exists():
            cookie_data = cookie_file.read_text().strip()
            username, password = cookie_data.split(":", 1)
            return username, password

        # Fallback to bitcoin.conf
        conf_file = self.data_dir / "bitcoin.conf"
        if conf_file.exists():
            config = self._parse_bitcoin_conf(conf_file)
            return config.get("rpcuser", ""), config.get("rpcpassword", "")

        raise FileNotFoundError(
            f"No credentials found. Checked:\n"
            f"  - {cookie_file}\n"
            f"  - {conf_file}"
        )

    def _parse_bitcoin_conf(self, conf_file: Path) -> dict:
        """Parse bitcoin.conf for RPC settings"""
        config = {}
        for line in conf_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                if "=" in line:
                    key, value = line.split("=", 1)
                    config[key.strip()] = value.strip()
        return config

    def call(self, method: str, params: list = None) -> dict:
        """Call Bitcoin Core RPC method"""
        payload = {
            "jsonrpc": "2.0",
            "id": "utxoracle",
            "method": method,
            "params": params or []
        }

        request = Request(
            self.rpc_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )

        # Add HTTP Basic Authentication
        auth_string = f"{self._rpc_user}:{self._rpc_password}"
        import base64
        auth_bytes = base64.b64encode(auth_string.encode()).decode()
        request.add_header("Authorization", f"Basic {auth_bytes}")

        try:
            with urlopen(request, timeout=self.timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
                if "error" in result and result["error"]:
                    raise RPCError(result["error"])
                return result.get("result")
        except URLError as e:
            raise ConnectionError(f"Failed to connect to Bitcoin Core: {e}")

    def test_connection(self) -> bool:
        """Test RPC connection"""
        try:
            info = self.call("getblockchaininfo")
            return info is not None
        except Exception:
            return False


class RPCError(Exception):
    """Bitcoin RPC error"""
    pass


# Usage example
if __name__ == "__main__":
    rpc = BitcoinRPC()
    if rpc.test_connection():
        print("✅ Connected to Bitcoin Core")
        info = rpc.call("getblockchaininfo")
        print(f"Blocks: {info['blocks']}")
    else:
        print("❌ Failed to connect")
```

## Templates

### 1. Minimal RPC Client Template
```python
import json
from pathlib import Path
from urllib.request import Request, urlopen

class BitcoinRPC:
    def __init__(self, data_dir: Path = Path.home() / ".bitcoin"):
        self.data_dir = data_dir
        self.rpc_url = "http://127.0.0.1:8332"
        self._load_credentials()

    def _load_credentials(self):
        cookie = (self.data_dir / ".cookie").read_text().strip()
        self.user, self.password = cookie.split(":", 1)

    def call(self, method: str, params: list = None) -> dict:
        # Implementation...
        pass
```

### 2. Async RPC Client Template
```python
import aiohttp
import json
from pathlib import Path
from typing import Optional

class AsyncBitcoinRPC:
    """Async Bitcoin Core RPC client"""

    def __init__(
        self,
        rpc_url: str = "http://127.0.0.1:8332",
        data_dir: Optional[Path] = None
    ):
        self.rpc_url = rpc_url
        self.data_dir = data_dir or Path.home() / ".bitcoin"
        self._session: Optional[aiohttp.ClientSession] = None
        self._auth = self._get_auth()

    def _get_auth(self) -> aiohttp.BasicAuth:
        """Load RPC credentials"""
        cookie_file = self.data_dir / ".cookie"
        user, password = cookie_file.read_text().strip().split(":", 1)
        return aiohttp.BasicAuth(user, password)

    async def __aenter__(self):
        self._session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, *args):
        if self._session:
            await self._session.close()

    async def call(self, method: str, params: list = None) -> dict:
        """Call RPC method asynchronously"""
        payload = {
            "jsonrpc": "2.0",
            "id": "utxoracle",
            "method": method,
            "params": params or []
        }

        async with self._session.post(
            self.rpc_url,
            json=payload,
            auth=self._auth
        ) as response:
            result = await response.json()
            if result.get("error"):
                raise RPCError(result["error"])
            return result.get("result")


# Usage
async def main():
    async with AsyncBitcoinRPC() as rpc:
        info = await rpc.call("getblockchaininfo")
        print(f"Blocks: {info['blocks']}")
```

### 3. RPC with Retry Logic
```python
import time
from functools import wraps

def retry_on_failure(max_attempts=3, delay=1):
    """Decorator for RPC retry logic"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except (ConnectionError, URLError) as e:
                    if attempt == max_attempts - 1:
                        raise
                    time.sleep(delay * (2 ** attempt))  # Exponential backoff
            return None
        return wrapper
    return decorator

class ResilientBitcoinRPC(BitcoinRPC):
    @retry_on_failure(max_attempts=5, delay=2)
    def call(self, method: str, params: list = None) -> dict:
        return super().call(method, params)
```

### 4. RPC Connection Pool
```python
from queue import Queue
from threading import Lock

class BitcoinRPCPool:
    """Connection pool for Bitcoin RPC"""

    def __init__(self, pool_size: int = 5):
        self.pool_size = pool_size
        self._pool = Queue(maxsize=pool_size)
        self._lock = Lock()

        # Initialize pool
        for _ in range(pool_size):
            self._pool.put(BitcoinRPC())

    def acquire(self) -> BitcoinRPC:
        """Get RPC connection from pool"""
        return self._pool.get()

    def release(self, rpc: BitcoinRPC):
        """Return RPC connection to pool"""
        self._pool.put(rpc)

    def call(self, method: str, params: list = None) -> dict:
        """Call RPC using pool connection"""
        rpc = self.acquire()
        try:
            return rpc.call(method, params)
        finally:
            self.release(rpc)
```

## Usage Patterns

### Pattern 1: Cookie Authentication (Default)
```
User: "Connect to Bitcoin Core with cookie auth"

Skill:
1. Detect OS (Linux/macOS/Windows)
2. Find Bitcoin data directory
3. Read .cookie file
4. Parse username:password
5. Create RPC client with HTTP Basic Auth
```

### Pattern 2: bitcoin.conf Authentication
```
User: "Connect using bitcoin.conf credentials"

Skill:
1. Parse bitcoin.conf
2. Extract rpcuser and rpcpassword
3. Create RPC client
4. Add fallback to .cookie if conf missing
```

### Pattern 3: Async RPC Client
```
User: "Create async Bitcoin RPC client"

Skill:
1. Use aiohttp instead of urllib
2. Add async/await methods
3. Include context manager (__aenter__/__aexit__)
4. Add connection pooling
```

### Pattern 4: Production RPC with Retry
```
User: "Create production-ready RPC with retries"

Skill:
1. Add exponential backoff decorator
2. Include connection health checks
3. Add logging
4. Include timeout configuration
```

## OS Path Detection

Auto-detect Bitcoin data directory:
```python
def detect_bitcoin_datadir() -> Path:
    """Detect Bitcoin data directory for current OS"""
    system = platform.system()

    paths = {
        "Linux": Path.home() / ".bitcoin",
        "Darwin": Path.home() / "Library" / "Application Support" / "Bitcoin",
        "Windows": Path(os.environ.get("APPDATA", "")) / "Bitcoin"
    }

    data_dir = paths.get(system)
    if not data_dir or not data_dir.exists():
        raise FileNotFoundError(
            f"Bitcoin data directory not found for {system}.\n"
            f"Expected: {data_dir}\n"
            f"Install Bitcoin Core or specify custom path."
        )

    return data_dir
```

## RPC Methods Library

Common Bitcoin Core RPC methods:
```python
class BitcoinRPCMethods:
    """Convenient method wrappers"""

    def get_blockchain_info(self) -> dict:
        return self.call("getblockchaininfo")

    def get_block_count(self) -> int:
        return self.call("getblockcount")

    def get_block_hash(self, height: int) -> str:
        return self.call("getblockhash", [height])

    def get_block(self, block_hash: str, verbosity: int = 1) -> dict:
        return self.call("getblock", [block_hash, verbosity])

    def get_raw_mempool(self, verbose: bool = False) -> dict:
        return self.call("getrawmempool", [verbose])

    def get_mempool_info(self) -> dict:
        return self.call("getmempoolinfo")

    def send_raw_transaction(self, hex_tx: str) -> str:
        return self.call("sendrawtransaction", [hex_tx])

    def decode_raw_transaction(self, hex_tx: str) -> dict:
        return self.call("decoderawtransaction", [hex_tx])
```

## Error Handling

Auto-include comprehensive error handling:
```python
class RPCError(Exception):
    """Bitcoin RPC returned an error"""
    def __init__(self, error_dict: dict):
        self.code = error_dict.get("code")
        self.message = error_dict.get("message")
        super().__init__(f"RPC Error {self.code}: {self.message}")

class ConnectionError(Exception):
    """Failed to connect to Bitcoin Core"""
    pass

class AuthenticationError(Exception):
    """RPC authentication failed"""
    pass

class TimeoutError(Exception):
    """RPC call timed out"""
    pass

def handle_rpc_errors(response: dict):
    """Parse RPC response for errors"""
    if "error" in response and response["error"]:
        error = response["error"]
        if error.get("code") == -401:
            raise AuthenticationError("Invalid RPC credentials")
        elif error.get("code") == -28:
            raise ConnectionError("Bitcoin Core is still starting up")
        else:
            raise RPCError(error)
```

## Configuration File Template

Auto-generate `bitcoin_rpc_config.py`:
```python
"""
Bitcoin Core RPC Configuration

Customize connection settings here.
"""
from pathlib import Path
import os

# RPC Endpoint
RPC_URL = os.getenv("BITCOIN_RPC_URL", "http://127.0.0.1:8332")

# Data Directory (auto-detected if None)
DATA_DIR = None  # Or: Path("/custom/path/.bitcoin")

# Timeouts
RPC_TIMEOUT = 30  # seconds
CONNECT_TIMEOUT = 10

# Retry Settings
MAX_RETRIES = 5
RETRY_DELAY = 2  # seconds

# Connection Pool
POOL_SIZE = 5

# Logging
LOG_RPC_CALLS = False  # Set True for debugging
```

## Output Format

**Generated RPC client file** (`live/backend/bitcoin_rpc.py`):
```python
"""
Bitcoin Core RPC Client

Auto-generated by bitcoin-rpc-connector Skill.
Handles authentication, OS path detection, and error handling.
"""
import json
import platform
from pathlib import Path
from typing import Optional
from urllib.request import Request, urlopen

# Class definitions here...

# Usage example and tests
if __name__ == "__main__":
    # Test connection
    rpc = BitcoinRPC()
    print("Testing Bitcoin Core connection...")

    if rpc.test_connection():
        print("✅ Connected successfully")
        info = rpc.call("getblockchaininfo")
        print(f"  Chain: {info['chain']}")
        print(f"  Blocks: {info['blocks']}")
        print(f"  Headers: {info['headers']}")
    else:
        print("❌ Connection failed")
```

## Automatic Invocation

**Triggers**:
- "create bitcoin rpc client"
- "connect to bitcoin core"
- "bitcoin rpc connection"
- "setup bitcoin core rpc"
- "rpc client with cookie auth"
- "async bitcoin rpc"

**Does NOT trigger**:
- Complex RPC logic (use subagent)
- Custom RPC server implementation
- Non-Bitcoin RPC connections

## Integration with UTXOracle

### In Configuration (`live/backend/config.py`)
```python
from bitcoin_rpc import BitcoinRPC

# Initialize RPC at startup
bitcoin_rpc = BitcoinRPC()

# Verify connection
if not bitcoin_rpc.test_connection():
    raise ConnectionError("Cannot connect to Bitcoin Core")
```

### In ZMQ Listener (`live/backend/zmq_listener.py`)
```python
from bitcoin_rpc import BitcoinRPC

class ZMQListener:
    def __init__(self):
        self.rpc = BitcoinRPC()  # Used for RPC fallback

    async def get_block_by_hash(self, block_hash: str):
        """Fetch block via RPC if ZMQ misses it"""
        return self.rpc.call("getblock", [block_hash])
```

### In Mempool Analyzer (`live/backend/mempool_analyzer.py`)
```python
from bitcoin_rpc import BitcoinRPC

class MempoolAnalyzer:
    def __init__(self):
        self.rpc = BitcoinRPC()

    def get_mempool_snapshot(self) -> dict:
        """Get current mempool state"""
        return self.rpc.call("getrawmempool", [True])
```

## Token Savings

| Task | Without Skill | With Skill | Savings |
|------|--------------|------------|---------|
| Basic RPC client | ~1,000 tokens | ~400 tokens | 60% |
| With OS detection | ~1,500 tokens | ~600 tokens | 60% |
| Async RPC | ~1,800 tokens | ~700 tokens | 61% |
| Production-ready (retries) | ~2,500 tokens | ~1,000 tokens | 60% |

**Average Savings**: 60% (2,500 → 1,000 tokens)

## Testing Template

Auto-generate RPC tests:
```python
# tests/test_bitcoin_rpc.py
import pytest
from live.backend.bitcoin_rpc import BitcoinRPC

def test_rpc_connection():
    """Test RPC connects to Bitcoin Core"""
    rpc = BitcoinRPC()
    assert rpc.test_connection() == True

def test_get_blockchain_info():
    """Test getblockchaininfo RPC call"""
    rpc = BitcoinRPC()
    info = rpc.call("getblockchaininfo")
    assert "chain" in info
    assert "blocks" in info

def test_os_path_detection():
    """Test Bitcoin data directory auto-detection"""
    rpc = BitcoinRPC()
    assert rpc.data_dir.exists()
    assert (rpc.data_dir / "blocks").exists()
```
