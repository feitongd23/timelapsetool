# skyfire 小程序(自用 v1)

## 跑起来
1. Mac 上起 API:`cd ../skyfire && .venv/bin/skyfire serve`
2. 微信开发者工具 → 导入项目 → 选本目录(AppID 已在 project.config.json)
3. 改代码时 `npm run dev:weapp` 保持编译(Node 在 `~/.local/node/bin`,终端需
   `export PATH="$HOME/.local/node/bin:$PATH"`);工具加载 `dist/`
4. 模拟器直接可用(urlCheck 已关);真机预览:把 `src/api/client.ts` 的
   `API_BASE` 改成 Mac 局域网 IP(系统设置→Wi-Fi 查看),手机与 Mac 同一 WiFi

## 手测清单(每次改版过一遍)
- [ ] 登录页一键登录 → 进首页(首次);杀掉重开不再要求登录
- [ ] 首页今天/明天下拉;朝霞/晚霞 tab;已结束事件带角标且数字淡化
- [ ] hero 大数字/定性词与 `skyfire latest` 输出一致
- [ ] 在"明天"tab 下拉刷新,tab 选中不跳变
- [ ] 轨迹曲线点数 = 该事件 predictions 行数;标签顺序 展望→C1→门控→C2→C3;
      圆点是正圆不是椭圆(dpr 修复的验收点)
- [ ] 各模式行 4 行,降水≥0.1mm 标红,缺数据显示 —
- [ ] 热力图骨架屏→1-3 秒浮现;点图全屏;切 tab 再切回秒出(API 缓存)
- [ ] 断网/关 serve 后热力图报错,"点我重试"真的会重拉
- [ ] 解读卡文字与 Bark 推送一致;pending 时显示"解读暂缺"
- [ ] 下拉刷新生效;关掉 serve 重进显示"服务未启动"引导
