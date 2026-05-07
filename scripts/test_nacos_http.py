import httpx
import json

# 测试 Nacos HTTP API
server = "nlb-i43wngypl42w7kub36.cn-hongkong.nlb.aliyuncsslbintl.com:8848"
namespace = "ce2b18cc-e2ee-4673-a2a3-6b5b33309fb1"
data_id = "thvote-be"
group = "DEFAULT_GROUP"

print("Testing Nacos HTTP API...")
print(f"Server: {server}")
print(f"Namespace: {namespace}")
print(f"Data ID: {data_id}")
print(f"Group: {group}")
print("-" * 60)

# 1. 测试服务器健康状态
try:
    resp = httpx.get(f"http://{server}/nacos/v1/console/health/readiness", timeout=5)
    print(f"\n[1] Server health: {resp.status_code} - {resp.text[:200]}")
except Exception as e:
    print(f"\n[1] Server health error: {e}")

# 2. 测试获取配置
try:
    resp = httpx.get(
        f"http://{server}/nacos/v2/cs/config",
        params={"dataId": data_id, "group": group, "tenant": namespace},
        timeout=5,
    )
    print(f"\n[2] Get config: {resp.status_code}")
    if resp.status_code == 200:
        print(f"    Content length: {len(resp.text)}")
        print(f"    Content preview: {resp.text[:200]}")
    else:
        print(f"    Response: {resp.text}")
except Exception as e:
    print(f"\n[2] Get config error: {e}")

# 3. 测试获取命名空间列表
try:
    resp = httpx.get(f"http://{server}/nacos/v1/console/namespaces", timeout=5)
    print(f"\n[3] Get namespaces: {resp.status_code}")
    print(f"    Response: {resp.text[:500]}")
except Exception as e:
    print(f"\n[3] Get namespaces error: {e}")

# 4. 尝试登录获取 token
try:
    resp = httpx.post(
        f"http://{server}/nacos/v1/auth/login",
        data={"username": "nacos", "password": "nacos"},
        timeout=5,
    )
    print(f"\n[4] Login: {resp.status_code}")
    if resp.status_code == 200:
        result = resp.json()
        print(f"    Access token: {result.get('accessToken', 'N/A')[:50]}...")
    else:
        print(f"    Response: {resp.text[:200]}")
except Exception as e:
    print(f"\n[4] Login error: {e}")

print("\n" + "=" * 60)
