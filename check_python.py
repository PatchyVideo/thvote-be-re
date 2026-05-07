import sys
print("Python version:", sys.version)
print("\nPython path:")
for p in sys.path:
    print(f"  {p}")
print("\nInstalled packages with 'nacos':")
try:
    import pkg_resources
    for p in pkg_resources.working_set:
        if 'nacos' in p.key.lower():
            print(f"  {p.key}=={p.version}")
except:
    print("  pkg_resources not available")

print("\nChecking if nacos can be imported:")
try:
    import nacos
    print("  SUCCESS: nacos imported")
    print("  nacos module location:", nacos.__file__)
except ImportError as e:
    print(f"  FAILED: {e}")
