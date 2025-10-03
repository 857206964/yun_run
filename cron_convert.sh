#!/bin/bash

# Cron时间随机化脚本
# 作用：在指定小时范围内随机生成cron表达式，避免固定时间被检测

set -e

# 默认配置
DEFAULT_CRON_HOURS="8-22"
WORKFLOW_FILE=".github/workflows/step.yml"

# 日志函数
log_info() {
    echo "ℹ️  [INFO] \$1"
}

log_success() {
    echo "✅ [SUCCESS] \$1"
}

log_error() {
    echo "❌ [ERROR] \$1" >&2
}

# 生成随机数（范围：min-max）
random_number() {
    local min=\$1
    local max=\$2
    echo $((RANDOM % (max - min + 1) + min))
}

# 解析小时范围配置
# 支持格式：
#   - "8-22"  （范围）
#   - "9,12,15,18,21" （指定小时）
parse_hour_range() {
    local hour_config=\$1
    
    if [[ $hour_config =~ ^[0-9]+-[0-9]+$ ]]; then
        # 范围格式：8-22
        local start=$(echo $hour_config | cut -d'-' -f1)
        local end=$(echo $hour_config | cut -d'-' -f2)
        random_number $start $end
    elif [[ $hour_config =~ ^[0-9,]+$ ]]; then
        # 逗号分隔格式：9,12,15,18,21
        local hours_array=(${hour_config//,/ })
        local random_index=$(random_number 0 $((${#hours_array[@]} - 1)))
        echo ${hours_array[$random_index]}
    else
        log_error "无效的小时配置格式: $hour_config"
        echo 10  # 默认返回10点
    fi
}

# 生成随机cron表达式
# 参数：\$1 = 小时范围配置（如："8-22"）
generate_random_cron() {
    local hour_config=${1:-$DEFAULT_CRON_HOURS}
    
    # 随机分钟：0-59
    local minute=$(random_number 0 59)
    
    # 随机小时（从配置中选择）
    local hour=$(parse_hour_range "$hour_config")
    
    # UTC时间需要减8小时（北京时间 - 8 = UTC）
    local utc_hour=$(( (hour - 8 + 24) % 24 ))
    
    # 生成cron表达式：分钟 小时 日 月 星期
    local cron_expr="${minute} ${utc_hour} * * *"
    
    log_info "随机生成 - 北京时间: ${hour}:${minute}, UTC时间: ${utc_hour}:${minute}"
    log_success "Cron表达式: $cron_expr"
    
    echo "$cron_expr"
}

# 更新workflow文件中的cron表达式
# 参数：\$1 = 新的cron表达式
update_workflow_cron() {
    local new_cron=\$1
    
    if [ ! -f "$WORKFLOW_FILE" ]; then
        log_error "找不到workflow文件: $WORKFLOW_FILE"
        return 1
    fi
    
    # 使用sed替换cron行
    # 匹配形如：    - cron: '30 2 * * *'
    sed -i "s|^\s*- cron:.*|    - cron: '$new_cron'  # 自动生成于 $(TZ=Asia/Shanghai date '+%Y-%m-%d %H:%M:%S')|" "$WORKFLOW_FILE"
    
    log_success "已更新 $WORKFLOW_FILE"
}

# 主函数：持久化执行并记录日志
# 参数：
#   \$1 = 触发事件类型（workflow_run/workflow_dispatch）
#   \$2 = 小时范围配置
persist_execute_log() {
    local trigger_event=${1:-"manual"}
    local hour_config=${2:-$DEFAULT_CRON_HOURS}
    
    log_info "=== Cron随机化开始 ==="
    log_info "触发方式: $trigger_event"
    log_info "小时范围: $hour_config"
    
    # 生成随机cron
    local new_cron=$(generate_random_cron "$hour_config")
    
    # 更新workflow文件
    update_workflow_cron "$new_cron"
    
    # 记录执行日志
    local log_file="cron_history.log"
    local timestamp=$(TZ=Asia/Shanghai date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] Event: $trigger_event | Cron: $new_cron" >> "$log_file"
    
    log_info "=== Cron随机化完成 ==="
    
    # 显示下次执行时间预测
    predict_next_run "$new_cron"
}

# 预测下次执行时间（仅供参考）
predict_next_run() {
    local cron_expr=\$1
    local minute=$(echo $cron_expr | awk '{print \$1}')
    local utc_hour=$(echo $cron_expr | awk '{print \$2}')
    local beijing_hour=$(( (utc_hour + 8) % 24 ))
    
    log_info "📅 下次执行时间（预计）: 北京时间每天 ${beijing_hour}:${minute}"
}

# 如果直接运行脚本（非source），则执行测试
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    log_info "🧪 测试模式"
    persist_execute_log "test" "8-22"
fi
