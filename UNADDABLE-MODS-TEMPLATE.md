# 实在加不进去的 Mod 记录（模板）

用于记录因为 `packwiz` 找不到合适版本、或需要手动挑版本/手动下载等原因，暂时没有纳入某个版本整包的 Mod/资源链接。

## 建议优先尝试

- Modrinth：优先用 `packwiz modrinth add --version-id <VERSION_ID>` 指定具体版本添加
- 直链：用 `packwiz url add` 兜底（缺点：不带 Modrinth/CF 自动更新信息）

## 记录模板（复制一份填写）

```md
### <Mod 名称>

- 链接：
  - Modrinth: <url>
  - CurseForge: <url>
  - GitHub/Release: <url>
- 目标版本：MC <x.y.z> / Loader <neoforge|forge|fabric>（如果有）
- 尝试结果：<packwiz 报错/原因简述>
- 备注：<依赖/兼容层/需要手动选版本ID等>
- 记录人：<name>
- 日期：<YYYY-MM-DD>
```

