"""
Nacos 配置中心连接测试脚本

用法:
    cd /d d:/personal/thvote
    python scripts/test_nacos.py
"""
import asyncio
import json
import os
import sys

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)


def get_config():
    return {
        "server_addresses": os.getenv("NACOS_SERVER_ADDRS", "http://154.37.215.62:8848"),
        "namespace": os.getenv("NACOS_NAMESPACE", "dfacd6e1-b442-476c-bffe-ff5504651c39"),
        "group": os.getenv("NACOS_GROUP", "DEFAULT_GROUP"),
        "data_id": os.getenv("NACOS_DATA_ID", "thvote_be"),
        "username": os.getenv("NACOS_USERNAME", "thvote_test"),
        "password": os.getenv("NACOS_PASSWORD", "test_thV0te"),
    }


async def test_nacos_client():
    """测试 NacosHTTPClient"""
    cfg = get_config()
    print("=" * 60)
    print("Nacos HTTP Client 测试")
    print("=" * 60)
    print(f"服务器: {cfg['server_addresses']}")
    print(f"命名空间: {cfg['namespace']}")
    print(f"分组: {cfg['group']}")
    print(f"Data ID: {cfg['data_id']}")
    print(f"用户名: {cfg['username']}")
    print("-" * 60)

    try:
        # 直接导入 nacos 模块（避免 __init__.py 的导入问题）
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "nacos_module",
            os.path.join(_project_root, "src", "common", "nacos.py")
        )
        nacos_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(nacos_module)

        NacosHTTPClient = nacos_module.NacosHTTPClient

        client = NacosHTTPClient(
            server_addresses=cfg["server_addresses"],
            namespace=cfg["namespace"],
            username=cfg["username"],
            password=cfg["password"],
            timeout=10.0,
        )

        print("正在获取配置...")
        content = await client.get_config(cfg["data_id"], cfg["group"])

        if content:
            print(f"配置获取成功! 长度: {len(content)} 字符")
            print("-" * 60)

            try:
                config_dict = json.loads(content)
                print("配置内容:")
                for k, v in config_dict.items():
                    if "PASSWORD" in k or "SECRET" in k or "KEY" in k:
                        print(f"  {k}: ***")
                    else:
                        print(f"  {k}: {v}")
                return config_dict
            except json.JSONDecodeError:
                print("原始内容:")
                print(content[:500])
                return {"raw": content}
        else:
            print("配置获取失败")
            return None

    except Exception as e:
        print(f"测试失败: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return None


async def test_load_nacos_overrides():
    """测试 load_nacos_overrides 函数"""
    cfg = get_config()
    print("\n" + "=" * 60)
    print("测试 load_nacos_overrides 函数")
    print("=" * 60)

    try:
        # 直接导入 nacos 模块
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "nacos_module",
            os.path.join(_project_root, "src", "common", "nacos.py")
        )
        nacos_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(nacos_module)

        load_nacos_overrides = nacos_module.load_nacos_overrides

        # 设置环境变量
        os.environ["NACOS_ENABLED"] = "true"
        os.environ["NACOS_SERVER_ADDRS"] = cfg["server_addresses"]
        os.environ["NACOS_NAMESPACE"] = cfg["namespace"]
        os.environ["NACOS_GROUP"] = cfg["group"]
        os.environ["NACOS_DATA_ID"] = cfg["data_id"]
        os.environ["NACOS_USERNAME"] = cfg["username"]
        os.environ["NACOS_PASSWORD"] = cfg["password"]

        config = load_nacos_overrides()

        if config:
            print(f"成功加载 {len(config)} 个配置项")
            return config
        else:
            print("配置加载失败")
            return None

    except Exception as e:
        print(f"测试失败: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    print("\n")

    result1 = asyncio.run(test_nacos_client())
    result2 = asyncio.run(test_load_nacos_overrides())

    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    print(f"NacosHTTPClient: {'通过' if result1 else '失败'}")
    print(f"load_nacos_overrides: {'通过' if result2 else '失败'}")

    sys.exit(0 if (result1 and result2) else 1)
