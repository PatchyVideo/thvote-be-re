# ============================================================
# THVote 测试环境管理脚本
#
# 使用方法:
#   docker/test-env.sh [start|stop|restart|logs|status|clean]
# ============================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${SCRIPT_DIR}/docker-compose.test.yml"

log_info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $1"; }

show_help() {
    cat << EOF
${CYAN}THVote 测试环境管理脚本${NC}

用法:
    docker/test-env.sh [命令]

命令:
    ${BLUE}start${NC}     启动所有测试环境服务
    ${BLUE}stop${NC}      停止所有测试环境服务
    ${BLUE}restart${NC}   重启所有测试环境服务
    ${BLUE}logs${NC}      查看所有服务日志
    ${BLUE}logs [服务]${NC} 查看指定服务日志
    ${BLUE}status${NC}    查看所有服务状态
    ${BLUE}clean${NC}      停止并删除所有数据（完全重置）
    ${BLUE}health${NC}     检查所有服务健康状态
    ${BLUE}backup${NC}     备份测试数据库
    ${BLUE}help${NC}       显示此帮助信息

服务:
    - postgres-test      PostgreSQL 数据库
    - redis-test        Redis 缓存
    - apollo-config-test Apollo 配置中心
    - backend-test      后端服务
    - frontend-test     前端 + Nginx
EOF
}

check_docker() {
    if ! docker info > /dev/null 2>&1; then
        log_error "Docker 未运行，请先启动 Docker Desktop"
        exit 1
    fi
}

cmd_start() {
    log_info "启动测试环境..."
    docker-compose -f ${COMPOSE_FILE} up -d
    log_success "测试环境启动完成！"
    cmd_status
}

cmd_stop() {
    log_info "停止测试环境..."
    docker-compose -f ${COMPOSE_FILE} down
    log_success "测试环境已停止"
}

cmd_restart() {
    log_info "重启测试环境..."
    docker-compose -f ${COMPOSE_FILE} restart
    log_success "测试环境重启完成"
}

cmd_logs() {
    if [ -n "$2" ]; then
        docker-compose -f ${COMPOSE_FILE} logs -f "$2"
    else
        docker-compose -f ${COMPOSE_FILE} logs -f
    fi
}

cmd_status() {
    echo ""
    echo -e "${CYAN}========== 测试环境服务状态 ==========${NC}"
    docker-compose -f ${COMPOSE_FILE} ps
    echo ""
    echo -e "${CYAN}========== 服务访问地址 ==========${NC}"
    echo -e "前端:     ${GREEN}http://localhost:8082${NC}"
    echo -e "后端API:  ${GREEN}http://localhost:8000${NC}"
    echo -e "健康检查: ${GREEN}http://localhost:8000/health${NC}"
    echo -e "Apollo:   ${GREEN}http://localhost:18080${NC}"
    echo ""
    echo -e "${CYAN}========== Apollo 配置 ==========${NC}"
    echo -e "请在 Apollo Portal 中配置以下项："
    echo -e "  DATABASE_URL=postgresql+asyncpg://thvote_test:thvote_test_pass@postgres-test:5432/thvote_test"
    echo -e "  REDIS_URL=redis://redis-test:6379/0"
    echo -e "  VOTE_YEAR=2025"
    echo ""
}

cmd_clean() {
    echo -e "${RED}警告：此操作将删除所有测试数据！${NC}"
    read -p "确定要继续吗？(输入 'yes' 确认): " confirm
    if [ "$confirm" = "yes" ]; then
        log_info "正在删除测试环境及数据..."
        docker-compose -f ${COMPOSE_FILE} down -v
        log_success "测试环境已完全清除"
    else
        log_info "已取消操作"
    fi
}

cmd_health() {
    echo ""
    echo -e "${CYAN}========== 健康检查 ==========${NC}"
    if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
        echo -e "后端: ${GREEN}健康${NC}"
    else
        echo -e "后端: ${RED}不健康${NC}"
    fi
    echo ""
}

cmd_backup() {
    BACKUP_DIR="./backup/test"
    mkdir -p ${BACKUP_DIR}
    BACKUP_FILE="${BACKUP_DIR}/pg_backup_$(date +%Y%m%d_%H%M%S).sql"
    log_info "正在备份测试数据库..."
    docker exec thvote-postgres-test pg_dump -U thvote_test thvote_test > "${BACKUP_FILE}"
    log_success "数据库已备份至: ${BACKUP_FILE}"
}

case "${1:-help}" in
    start)   cmd_start ;;
    stop)    cmd_stop ;;
    restart) cmd_restart ;;
    logs)    cmd_logs "$@" ;;
    status)  cmd_status ;;
    clean)   cmd_clean ;;
    health)  cmd_health ;;
    backup)  cmd_backup ;;
    help)    show_help ;;
    *)       show_help ;;
esac
