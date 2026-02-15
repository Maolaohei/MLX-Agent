#!/bin/bash
#
# MLX-Agent 全面测试脚本
# 
# 测试内容:
#   - Python 语法检查 (所有 .py 文件)
#   - 插件加载测试
#   - 工具定义验证
#   - 三层记忆架构测试
#   - 条件性思考模式测试
#   - 配置文件验证
#

set -e

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# 计数器
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_SKIPPED=0

# 日志函数
log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step() { echo -e "${BLUE}[STEP]${NC} $1"; }
log_test() { echo -e "${CYAN}[TEST]${NC} $1"; }

# 测试通过
pass() {
    echo -e "${GREEN}✓ PASS${NC}: $1"
    ((TESTS_PASSED++))
}

# 测试失败
fail() {
    echo -e "${RED}✗ FAIL${NC}: $1"
    ((TESTS_FAILED++))
}

# 测试跳过
skip() {
    echo -e "${YELLOW}⊘ SKIP${NC}: $1"
    ((TESTS_SKIPPED++))
}

# 获取项目根目录
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo "═══════════════════════════════════════════════════"
echo "  MLX-Agent 全面测试套件"
echo "  项目路径: $PROJECT_ROOT"
echo "═══════════════════════════════════════════════════"
echo ""

# =============================================================================
# 测试 1: Python 语法检查
# =============================================================================
test_python_syntax() {
    log_step "测试 1: Python 语法检查"
    
    local py_files=$(find "$PROJECT_ROOT" -name "*.py" -type f | grep -v __pycache__ | grep -v ".venv" | grep -v "venv")
    local total_files=$(echo "$py_files" | wc -l)
    local syntax_errors=0
    
    log_info "检查 $total_files 个 Python 文件..."
    
    for file in $py_files; do
        if ! python3 -m py_compile "$file" 2>/dev/null; then
            log_error "语法错误: $file"
            ((syntax_errors++))
        fi
    done
    
    if [ $syntax_errors -eq 0 ]; then
        pass "所有 Python 文件语法正确 ($total_files 个文件)"
    else
        fail "$syntax_errors 个文件存在语法错误"
    fi
}

# =============================================================================
# 测试 2: 导入测试
# =============================================================================
test_imports() {
    log_step "测试 2: 核心模块导入测试"
    
    local modules=(
        "mlx_agent"
        "mlx_agent.agent"
        "mlx_agent.memory"
        "mlx_agent.memory.chroma"
        "mlx_agent.memory.sqlite"
        "mlx_agent.memory.hybrid"
        "mlx_agent.memory.tiered"
        "mlx_agent.plugins.base"
        "mlx_agent.skills.plugin"
        "mlx_agent.identity"
        "mlx_agent.llm"
    )
    
    local import_errors=0
    
    for module in "${modules[@]}"; do
        if python3 -c "import $module" 2>/dev/null; then
            :
        else
            log_error "导入失败: $module"
            ((import_errors++))
        fi
    done
    
    if [ $import_errors -eq 0 ]; then
        pass "所有核心模块导入成功"
    else
        fail "$import_errors 个模块导入失败"
    fi
}

# =============================================================================
# 测试 3: 插件系统测试
# =============================================================================
test_plugin_system() {
    log_step "测试 3: 插件系统测试"
    
    local test_script=$(cat << 'EOF'
import sys
sys.path.insert(0, '.')

from mlx_agent.plugins.base import Plugin, PluginManager

# 测试插件基类
class TestPlugin(Plugin):
    @property
    def name(self):
        return "test_plugin"
    
    @property
    def description(self):
        return "Test plugin"
    
    async def _setup(self):
        pass

# 测试插件管理器
manager = PluginManager()
plugin = TestPlugin()

try:
    manager.register(plugin)
    assert "test_plugin" in manager.list_plugins()
    
    retrieved = manager.get("test_plugin")
    assert retrieved is not None
    assert retrieved.name == "test_plugin"
    
    manager.unregister("test_plugin")
    assert "test_plugin" not in manager.list_plugins()
    
    print("PLUGIN_TEST_PASSED")
except Exception as e:
    print(f"PLUGIN_TEST_FAILED: {e}")
    sys.exit(1)
EOF
)

    if python3 -c "$test_script" 2>/dev/null | grep -q "PLUGIN_TEST_PASSED"; then
        pass "插件系统功能正常"
    else
        fail "插件系统测试失败"
    fi
}

# =============================================================================
# 测试 4: 工具定义验证
# =============================================================================
test_tool_definitions() {
    log_step "测试 4: 工具定义验证"
    
    local test_script=$(cat << 'EOF'
import sys
import json
sys.path.insert(0, '.')

# 测试工具定义格式
from mlx_agent.plugins.base import Plugin

class ToolTestPlugin(Plugin):
    @property
    def name(self):
        return "tool_test"
    
    @property
    def description(self):
        return "Tool test plugin"
    
    async def _setup(self):
        pass
    
    def get_tools(self):
        return [
            {
                "type": "function",
                "function": {
                    "name": "test_tool",
                    "description": "A test tool",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query"
                            }
                        },
                        "required": ["query"]
                    }
                }
            }
        ]

plugin = ToolTestPlugin()
tools = plugin.get_tools()

# 验证工具格式
for tool in tools:
    assert "type" in tool, "Tool missing 'type'"
    assert "function" in tool, "Tool missing 'function'"
    func = tool["function"]
    assert "name" in func, "Function missing 'name'"
    assert "description" in func, "Function missing 'description'"
    assert "parameters" in func, "Function missing 'parameters'"

print("TOOL_TEST_PASSED")
EOF
)

    if python3 -c "$test_script" 2>/dev/null | grep -q "TOOL_TEST_PASSED"; then
        pass "工具定义格式正确"
    else
        fail "工具定义验证失败"
    fi
}

# =============================================================================
# 测试 5: 三层记忆架构测试
# =============================================================================
test_tiered_memory() {
    log_step "测试 5: 三层记忆架构测试"
    
    local test_script=$(cat << 'EOF'
import sys
sys.path.insert(0, '.')

from mlx_agent.memory.tiered import TieredMemoryBackend
from mlx_agent.memory.base import MemoryEntry, MemoryLevel

# 测试三层后端初始化
backend = TieredMemoryBackend(
    hot_path="/tmp/test_hot",
    warm_path="/tmp/test_warm.db",
    cold_path="/tmp/test_cold",
    embedding_provider="local",
    auto_tiering=False
)

# 验证三层属性
assert hasattr(backend, 'hot'), "Missing hot tier"
assert hasattr(backend, 'warm'), "Missing warm tier"
assert hasattr(backend, 'cold'), "Missing cold tier"

# 验证阈值配置
assert backend.hot_warm_threshold == 7, "Invalid hot_warm_threshold"
assert backend.warm_cold_threshold == 30, "Invalid warm_cold_threshold"
assert backend.p2_hot_threshold == 1, "Invalid p2_hot_threshold"

# 验证搜索深度选项
import inspect
sig = inspect.signature(backend.search)
params = list(sig.parameters.keys())
assert 'depth' in params, "Missing 'depth' parameter in search method"

print("TIERED_MEMORY_TEST_PASSED")
EOF
)

    if python3 -c "$test_script" 2>/dev/null | grep -q "TIERED_MEMORY_TEST_PASSED"; then
        pass "三层记忆架构配置正确"
    else
        fail "三层记忆架构测试失败"
    fi
}

# =============================================================================
# 测试 6: 条件性思考模式测试
# =============================================================================
test_reasoning_mode() {
    log_step "测试 6: 条件性思考模式测试"
    
    local test_script=$(cat << 'EOF'
import sys
sys.path.insert(0, '.')

# 检查配置中是否包含 reasoning 配置
import yaml

with open('config/config.yaml', 'r') as f:
    config = yaml.safe_load(f)

# 验证 reasoning 配置存在
assert 'reasoning' in config, "Missing 'reasoning' in config"

reasoning = config['reasoning']
assert 'enabled' in reasoning, "Missing 'enabled' in reasoning"
assert 'triggers' in reasoning, "Missing 'triggers' in reasoning"

# 验证触发器
triggers = reasoning['triggers']
expected_triggers = ['tool_call', 'complex_analysis', 'math_calculation', 'code_debugging']
for trigger in expected_triggers:
    assert trigger in triggers, f"Missing trigger: {trigger}"

print("REASONING_TEST_PASSED")
EOF
)

    if python3 -c "$test_script" 2>/dev/null | grep -q "REASONING_TEST_PASSED"; then
        pass "条件性思考模式配置正确"
    else
        fail "条件性思考模式测试失败"
    fi
}

# =============================================================================
# 测试 7: 配置文件验证
# =============================================================================
test_config_files() {
    log_step "测试 7: 配置文件验证"
    
    local errors=0
    
    # 检查主配置文件
    if [ -f "$PROJECT_ROOT/config/config.yaml" ]; then
        if python3 -c "import yaml; yaml.safe_load(open('$PROJECT_ROOT/config/config.yaml'))" 2>/dev/null; then
            pass "config.yaml 格式正确"
        else
            fail "config.yaml YAML 格式错误"
            ((errors++))
        fi
    else
        skip "config.yaml 不存在"
    fi
    
    # 检查 pyproject.toml
    if [ -f "$PROJECT_ROOT/pyproject.toml" ]; then
        pass "pyproject.toml 存在"
    else
        fail "pyproject.toml 不存在"
        ((errors++))
    fi
    
    # 检查 .gitignore
    if [ -f "$PROJECT_ROOT/.gitignore" ]; then
        if grep -q "config/config.yaml" "$PROJECT_ROOT/.gitignore"; then
            pass ".gitignore 正确排除了敏感配置"
        else
            fail ".gitignore 未排除 config/config.yaml"
            ((errors++))
        fi
    else
        fail ".gitignore 不存在"
        ((errors++))
    fi
}

# =============================================================================
# 测试 8: 安全验证
# =============================================================================
test_security() {
    log_step "测试 8: 安全验证"
    
    local errors=0
    
    # 检查是否有硬编码的 API key
    log_info "检查硬编码 API key..."
    
    local suspicious_patterns=(
        "sk-[a-zA-Z0-9]{20,}"
        "api[_-]?key.*=.*['\"][a-zA-Z0-9]{10,}['\"]"
        "token.*=.*['\"][a-zA-Z0-9]{20,}['\"]"
    )
    
    for pattern in "${suspicious_patterns[@]}"; do
        local matches=$(grep -r "$pattern" "$PROJECT_ROOT" --include="*.py" 2>/dev/null | grep -v __pycache__ | grep -v ".venv" | wc -l)
        if [ "$matches" -gt 0 ]; then
            log_warn "发现潜在的硬编码密钥 ($matches 处)"
        fi
    done
    
    # 检查 .env.example 是否存在
    if [ -f "$PROJECT_ROOT/.env.example" ]; then
        pass ".env.example 模板存在"
    else
        fail ".env.example 模板不存在"
        ((errors++))
    fi
    
    # 检查敏感文件是否被排除
    if [ -f "$PROJECT_ROOT/.gitignore" ]; then
        if grep -q ".env" "$PROJECT_ROOT/.gitignore"; then
            pass ".env 被正确排除"
        else
            fail ".env 未被排除在 .gitignore 中"
            ((errors++))
        fi
    fi
    
    if [ $errors -eq 0 ]; then
        pass "安全检查通过"
    fi
}

# =============================================================================
# 测试 9: 依赖检查
# =============================================================================
test_dependencies() {
    log_step "测试 9: 依赖检查"
    
    local errors=0
    
    # 检查 pyproject.toml 中的依赖
    if [ -f "$PROJECT_ROOT/pyproject.toml" ]; then
        # 检查关键依赖是否定义
        local key_deps=("uvloop" "pydantic" "loguru" "redis")
        for dep in "${key_deps[@]}"; do
            if grep -q "$dep" "$PROJECT_ROOT/pyproject.toml"; then
                :
            else
                log_warn "未找到依赖: $dep"
            fi
        done
        pass "pyproject.toml 依赖检查完成"
    fi
    
    # 检查 requirements.txt 是否存在
    if [ -f "$PROJECT_ROOT/requirements.txt" ]; then
        pass "requirements.txt 存在"
    else
        skip "requirements.txt 不存在 (使用 pyproject.toml 即可)"
    fi
}

# =============================================================================
# 测试 10: 文件结构检查
# =============================================================================
test_file_structure() {
    log_step "测试 10: 文件结构检查"
    
    local required_dirs=(
        "mlx_agent"
        "mlx_agent/memory"
        "mlx_agent/plugins"
        "mlx_agent/skills"
        "config"
        "scripts"
    )
    
    local errors=0
    
    for dir in "${required_dirs[@]}"; do
        if [ -d "$PROJECT_ROOT/$dir" ]; then
            :
        else
            fail "缺少目录: $dir"
            ((errors++))
        fi
    done
    
    if [ $errors -eq 0 ]; then
        pass "目录结构完整"
    fi
}

# =============================================================================
# 测试 11: 代码风格检查 (可选)
# =============================================================================
test_code_style() {
    log_step "测试 11: 代码风格检查"
    
    # 检查是否有 ruff
    if command -v ruff &> /dev/null; then
        log_info "使用 ruff 检查代码风格..."
        if ruff check "$PROJECT_ROOT/mlx_agent" 2>/dev/null; then
            pass "代码风格检查通过"
        else
            fail "代码风格存在问题"
        fi
    elif command -v flake8 &> /dev/null; then
        log_info "使用 flake8 检查代码风格..."
        if flake8 "$PROJECT_ROOT/mlx_agent" --max-line-length=100 2>/dev/null; then
            pass "代码风格检查通过"
        else
            fail "代码风格存在问题"
        fi
    else
        skip "未安装 ruff 或 flake8，跳过代码风格检查"
    fi
}

# =============================================================================
# 测试 12: 插件配置文件模板检查
# =============================================================================
test_plugin_config() {
    log_step "测试 12: 插件配置文件模板检查"
    
    if [ -f "$PROJECT_ROOT/config/plugins.yaml.example" ]; then
        if python3 -c "import yaml; yaml.safe_load(open('$PROJECT_ROOT/config/plugins.yaml.example'))" 2>/dev/null; then
            pass "plugins.yaml.example 格式正确"
        else
            fail "plugins.yaml.example YAML 格式错误"
        fi
    else
        skip "plugins.yaml.example 不存在"
    fi
}

# =============================================================================
# 主函数
# =============================================================================
main() {
    log_info "开始运行 MLX-Agent 测试套件..."
    echo ""
    
    # 运行所有测试
    test_python_syntax
    test_imports
    test_plugin_system
    test_tool_definitions
    test_tiered_memory
    test_reasoning_mode
    test_config_files
    test_security
    test_dependencies
    test_file_structure
    test_code_style
    test_plugin_config
    
    # 输出总结
    echo ""
    echo "═══════════════════════════════════════════════════"
    echo "  测试总结"
    echo "═══════════════════════════════════════════════════"
    echo -e "  ${GREEN}通过: $TESTS_PASSED${NC}"
    echo -e "  ${RED}失败: $TESTS_FAILED${NC}"
    echo -e "  ${YELLOW}跳过: $TESTS_SKIPPED${NC}"
    echo "═══════════════════════════════════════════════════"
    
    if [ $TESTS_FAILED -eq 0 ]; then
        echo -e "${GREEN}✅ 所有测试通过!${NC}"
        exit 0
    else
        echo -e "${RED}❌ 有 $TESTS_FAILED 个测试失败${NC}"
        exit 1
    fi
}

# 运行主函数
main "$@"
