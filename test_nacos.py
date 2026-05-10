import urllib.request

url = "http://154.37.215.62:8848/nacos/v1/cs/configs?dataId=thvote_be&group=DEFAULT_GROUP&namespaceId=dfacd6e1-b442-476c-bffe-ff5504651c39"
print("Fetching:", url)
r = urllib.request.urlopen(url, timeout=5)
content = r.read().decode()
print("Status: OK")
print("Content length:", len(content))
print("Content:", content[:500] if content else "EMPTY")
