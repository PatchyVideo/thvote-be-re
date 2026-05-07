#!/usr/bin/env python3
"""
Nacos 配置中心连接测试脚本

使用方法:
1. 设置环境变量 (或创建 .env 文件):
   - NACOS_SERVER_ADDRS: Nacos 服务器地址，如 "127.0.0.1:8848"
   - NACOS_NAMESPACE: 命名空间 ID，如 "ce2b18cc-e2ee-4673-a2a3-6b5b33309fb1"
   - NACOS_DATA_ID: 配置 dataId，如 "thvote-be"
   - NACOS_USERNAME: 用户名 (可选)
   - NACOS_PASSWORD: 密码 (可选)

2. 运行脚本:
   python scripts/test_nacos.py

   或直接指定参数:
   python scripts/test_nacos.py --server 127.0.0.1:8848 --namespace ce2b18cc-e2ee-4673-a2a3-6b5b33309fb1 --data-id thvote-be
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

# 添加 scripts 目录到路径
scripts_dir = Path(__file__).parent
sys.path.insert(0, str(scripts_dir))

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def test_nacos_connection(
    server: str,
    namespace: str,
    data_id: str,
    group: str = "DEFAULT_GROUP",
    username: str | None = None,
    password: str | None = None,
) -> bool:
    """测试 Nacos 连接"""
    from nacos_client import NacosConfigClient

    logger.info("=" * 60)
    logger.info("Nacos Connection Test")
    logger.info("=" * 60)
    logger.info("Server: %s", server)
    logger.info("Namespace: %s", namespace)
    logger.info("Group: %s", group)
    logger.info("Data ID: %s", data_id)
    if username:
        logger.info("Username: %s", username)
    logger.info("-" * 60)

    try:
        client = NacosConfigClient(
            server_addresses=server,
            namespace=namespace,
            group=group,
            username=username,
            password=password,
            log_level="DEBUG",
        )
        logger.info("[OK] Nacos client created successfully")

        logger.info("\n[Test 1] Getting config...")
        content = await client.get_config(data_id, group)
        if content is None:
            logger.warning("[FAIL] Config not found: dataId=%s, group=%s", data_id, group)
            return False

        logger.info("[OK] Config retrieved, length: %d bytes", len(content))
        logger.debug("Config content:\n%s", content[:500])

        logger.info("\n[Test 2] Parsing config as JSON...")
        try:
            config_dict = json.loads(content)
            logger.info("[OK] Config parsed as JSON, keys: %d", len(config_dict))
            logger.info("Config keys: %s", list(config_dict.keys()))
        except json.JSONDecodeError:
            logger.warning("[WARN] Config is not valid JSON, trying as properties format...")
            config_dict = await client.get_config_as_dict(data_id, group)
            if config_dict:
                logger.info("[OK] Config parsed as properties, keys: %d", len(config_dict))
                logger.info("Config keys: %s", list(config_dict.keys()))
            else:
                logger.error("[FAIL] Unable to parse config content")
                return False

        logger.info("\n[Test 3] Publishing test config...")
        test_data_id = f"{data_id}.test"
        test_content = json.dumps({"test_key": "test_value", "timestamp": "test"}, ensure_ascii=False)
        success = await client.publish_config(test_data_id, test_content, group)
        if success:
            logger.info("[OK] Test config published")
            logger.info("\n[Test 4] Removing test config...")
            await client.remove_config(test_data_id, group)
            logger.info("[OK] Test config removed")
        else:
            logger.warning("[SKIP] Publish test skipped")

        logger.info("\n[Test 5] Shutting down client...")
        await client.shutdown()
        logger.info("[OK] Client shutdown")

        logger.info("\n" + "=" * 60)
        logger.info("All tests passed!")
        logger.info("=" * 60)
        return True

    except Exception as exc:
        logger.error("\n[FAIL] Connection failed: %s", exc)
        logger.exception("Detailed error:")
        return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Test Nacos configuration center connection",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Use environment variables from .env file
  python scripts/test_nacos.py

  # Specify parameters directly
  python scripts/test_nacos.py --server 127.0.0.1:8848 --namespace ce2b18cc-e2ee-4673-a2a3-6b5b33309fb1

  # With authentication
  python scripts/test_nacos.py --server 127.0.0.1:8848 --namespace my-ns --username nacos --password nacos
        """,
    )

    parser.add_argument(
        "--server",
        type=str,
        default=os.getenv("NACOS_SERVER_ADDRS", "127.0.0.1:8848"),
        help="Nacos server address (default: from NACOS_SERVER_ADDRS env or 127.0.0.1:8848)",
    )
    parser.add_argument(
        "--namespace",
        type=str,
        default=os.getenv("NACOS_NAMESPACE", ""),
        help="Namespace ID (default: from NACOS_NAMESPACE env or public namespace)",
    )
    parser.add_argument(
        "--data-id",
        type=str,
        default=os.getenv("NACOS_DATA_ID", "thvote-be"),
        help="Config data ID (default: from NACOS_DATA_ID env or thvote-be)",
    )
    parser.add_argument(
        "--group",
        type=str,
        default=os.getenv("NACOS_GROUP", "DEFAULT_GROUP"),
        help="Config group (default: from NACOS_GROUP env or DEFAULT_GROUP)",
    )
    parser.add_argument(
        "--username",
        type=str,
        default=os.getenv("NACOS_USERNAME", ""),
        help="Nacos username for authentication",
    )
    parser.add_argument(
        "--password",
        type=str,
        default=os.getenv("NACOS_PASSWORD", ""),
        help="Nacos password for authentication",
    )

    args = parser.parse_args()

    if not args.server:
        logger.error("Nacos server address is required. Use --server or set NACOS_SERVER_ADDRS")
        return 1

    # 使用 asyncio 运行异步测试
    success = asyncio.run(
        test_nacos_connection(
            server=args.server,
            namespace=args.namespace,
            data_id=args.data_id,
            group=args.group,
            username=args.username or None,
            password=args.password or None,
        )
    )

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
