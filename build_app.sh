#!/usr/bin/env bash
#
# 打包桌面宠物 – Mac (py2app)
#

set -e        # 出错即退出

# 可选：创建 / 更新虚拟环境
# python3 -m venv .venv && source .venv/bin/activate
# pip install -U pip setuptools wheel

echo "🔄 清理旧产物…"
rm -rf build dist

echo "📦 开始打包…"
python setup.py py2app -A   # -A=alias 模式调试；正式版去掉 -A

echo "✅ 打包完成！"
echo "   产物路径：dist/DesktopPet.app"
