# ============================================================
# THVote 本地开发 Makefile
#
# 用法:
#   make help              查看所有可用命令
#   make up                启动后端 + 基础设施
#   make up-frontend       启动后端 + 前端
#   make down              停止所有服务
#   make logs              查看日志
#   make ps                查看服务状态
#   make backend-logs      查看后端日志
#   make frontend-logs     查看前端日志
#   make restart-backend   重启后端
#   make restart-frontend  重启前端
# ============================================================

.PHONY: help up up-frontend down logs ps backend-logs frontend-logs restart-backend restart-frontend

# 默认环境（test 或 prod）
ENV ?= test
COMPOSE_FILE = -f docker/docker-compose.yml

help:
	@echo "THVote 本地开发命令"
	@echo ""
	@echo "  make up               启动后端 + 基础设施（前端不启动）"
	@echo "  make up-frontend      启动后端 + 前端（需要先启动后端）"
	@echo "  make down             停止所有服务"
	@echo "  make logs             查看所有服务日志"
	@echo "  make ps               查看服务状态"
	@echo "  make backend-logs     查看后端日志"
	@echo "  make frontend-logs   查看前端日志"
	@echo "  make restart-backend  重启后端"
	@echo "  make restart-frontend 重启前端"
	@echo ""
	@echo "环境变量:"
	@echo "  ENV=test   使用测试环境配置（默认）"
	@echo "  ENV=prod   使用生产环境配置"
	@echo ""
	@echo "示例:"
	@echo "  ENV=prod make up-frontend"

# 启动后端 + 基础设施（前端不启动）
up:
	@echo "启动后端服务 (ENV=$(ENV))..."
	cd docker && \
	cp -n ../.env.$(ENV) .env 2>/dev/null || \
	echo "警告: .env.$(ENV) 不存在，请手动创建"; \
	docker compose $(COMPOSE_FILE) --profile backend up -d
	@echo ""
	@echo "后端已启动，请访问: http://localhost:8000"
	@echo "GraphQL: http://localhost:8000/graphql"
	@echo "Apollo: http://localhost:8070 (需要 APOLLO_ENABLED=yes)"
	@echo ""
	@echo "前端尚未启动。如需启动前端，请运行: make up-frontend"

# 启动后端 + 前端（完整环境）
up-frontend:
	@echo "启动完整服务 (后端 + 前端)..."
	cd docker && \
	docker compose $(COMPOSE_FILE) --profile backend up -d && \
	echo "等待后端就绪..." && \
	for i in $$(seq 1 30); do \
		if docker compose $(COMPOSE_FILE) exec -T backend curl -sf http://localhost:8000/health > /dev/null 2>&1; then \
			echo "后端就绪"; \
			break; \
		fi; \
		echo "等待后端... ($$i/30)"; \
		sleep 2; \
	done; \
	docker compose $(COMPOSE_FILE) --profile frontend up -d
	@echo ""
	@echo "服务启动完成!"
	@echo "  Vote:     http://localhost:8082"
	@echo "  Navigator: http://localhost:8083"
	@echo "  Result:   http://localhost:8084"
	@echo "  Backend:  http://localhost:8000"

# 停止所有服务
down:
	@echo "停止所有服务..."
	cd docker && docker compose $(COMPOSE_FILE) down

# 查看所有日志
logs:
	cd docker && docker compose $(COMPOSE_FILE) logs -f

# 查看服务状态
ps:
	cd docker && docker compose $(COMPOSE_FILE) ps

# 查看后端日志
backend-logs:
	cd docker && docker compose $(COMPOSE_FILE) logs -f backend

# 查看前端日志
frontend-logs:
	cd docker && docker compose $(COMPOSE_FILE) logs -f vote navigator result

# 重启后端
restart-backend:
	@echo "重启后端..."
	cd docker && docker compose $(COMPOSE_FILE) restart backend

# 重启前端
restart-frontend:
	@echo "重启前端..."
	cd docker && docker compose $(COMPOSE_FILE) restart vote navigator result

# 清理未使用的镜像
clean-images:
	@echo "清理未使用的 Docker 镜像..."
	docker image prune -f

# 完全重建（删除数据卷）
rebuild: down
	@echo "删除数据卷..."
	cd docker && docker compose $(COMPOSE_FILE) down -v
	@echo "数据卷已删除。重新启动请运行: make up"
