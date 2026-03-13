# 停止 Node 進程
Get-Process -Name node -ErrorAction SilentlyContinue | Stop-Process -Force

# 清理緩存
Remove-Item -Recurse -Force node_modules\.vite -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force .vite -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force dist -ErrorAction SilentlyContinue

Write-Host "Cache cleared! Now run: npm run dev"
