# ============================================================
# SSL 证书目录
#
# 此目录用于存放 SSL 证书文件
#
# 所需文件：
#   - server.crt    : 服务器证书（含中间证书）
#   - server.key    : 私钥文件
#
# 获取方式：
#   1. Let's Encrypt (推荐 - 免费)
#      - 使用 certbot 自动获取和续期
#      - certbot --nginx -d yourdomain.com
#
#   2. 商业证书
#      - 从证书颁发机构购买
#
#   3. 自签名证书 (仅用于测试)
#      - openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
#          -keyout server.key -out server.crt
#
# 安全提示：
#   - server.key 必须保密，不要提交到版本控制
#   - 建议在 .gitignore 中添加 *.key 和 *.crt
# ============================================================

# 占位文件 - 请用实际证书替换
PLACEHOLDER.txt
