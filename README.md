# 🧱 custom_mcpack

## 📌 项目概述

本仓库用于管理 **多个自定义 Minecraft 整合包（Modpack）**。  
每一个整合包实例（通常对应 **Minecraft 版本 + Mod Loader + 配置变体**）均作为 **独立目录** 进行维护，例如：

```
packs/1.21.1-neoforge-v1/
packs/1.20.1-fabric-v2/
```

每个目录都代表一个 **可复现、可迁移、可长期维护** 的整合包定义。

与传统“只保存本地 JAR 文件”的方式不同，本仓库 **以元数据为核心**，统一使用 `packwiz` 对 Mod 进行声明式管理，从而实现更可靠的版本控制与升级能力。

---

## 🎯 设计目标与动机

该仓库结构主要用于解决以下长期维护问题：

- 🔄 **更容易升级 Minecraft / Loader 版本**  
  同一批 Mod 可基于元数据快速迁移到新版本，而无需手动重新筛选和添加。

- ♻️ **减少重复劳动**  
  多个整合包实例之间可复用 Mod 定义，避免反复对比 JAR 文件。

- 🧪 **可复现性与可审计性**  
  每个 Mod 的来源、版本、校验信息均被明确记录，可在任意时间重新构建。

- 🛠️ **工程化管理方式**  
  以“依赖管理”的思路维护 Modpack，而非一次性整合。

---

## 🗂️ 整合包目录结构

每个整合包目录均使用 **`packwiz` 作为唯一的元数据管理工具**，典型结构如下：

```
pack.toml
index.toml
mods/
  ├── example-mod.pw.toml
  └── another-mod.pw.toml
docs/
  └── unaddable-mods.txt
```

📄 各文件说明：

- **`pack.toml`**  
  整合包基础信息（Minecraft 版本、Loader 类型、名称等）

- **`index.toml`**  
  由 packwiz 自动生成的文件索引

- **`mods/*.pw.toml`**  
  单个 Mod 的元数据定义（来源、版本、哈希等）

- **`docs/unaddable-mods.txt`**  
  无法通过 packwiz 管理的 Mod 记录文件

---

## 🚫 无法直接加入的 Mod（Unaddable Mods）

部分 Mod 由于以下原因 **无法直接通过 packwiz 管理**：

- ⛔ 需要手动下载
- 📜 许可证或分发方式受限
- 📦 使用外部安装器
- ⚠️ 非标准 Mod 分发格式

统一约定如下：

- **仓库根目录**  
  `UNADDABLE-MODS-TEMPLATE.md`  
  用于说明“无法加入的 Mod 应如何记录”的统一模板

- **每个整合包实例**  
  仅维护自身的具体记录文件，例如：

  ```
  packs/1.21.1-neoforge-v1/docs/unaddable-mods.txt
  ```

该机制用于确保 **例外情况被明确记录，而不是被隐式忽略**。

---

## 🧰 工具链说明

### 📦 packwiz（元数据管理）

本仓库使用 **packwiz** 作为 Mod 元数据管理的核心工具：

- 🔗 项目地址  
  https://github.com/packwiz/packwiz

请按照 packwiz 官方仓库中的说明完成安装。  
安装完成后，packwiz 主要用于：

- 初始化整合包
- 添加 / 更新 / 移除 Mod
- 维护 `pack.toml`、`index.toml` 与 `*.pw.toml` 文件

> ⚠️ **重要说明**  
> 在本仓库中，`packwiz` 是唯一权威的数据来源（Single Source of Truth）。  
> 不建议通过手动增删 JAR 文件的方式维护 Mod。

---

### ⬇️ packwiz-install（下载 Mod JAR 文件）

`packwiz` 仅负责 **元数据管理**，并不直接下载 Mod JAR 文件。  
实际下载与部署 Mod 文件时，使用：

- 🔗 项目地址  
  https://github.com/ookkoouu/packwiz-install

推荐流程：

1. 使用 `packwiz` 管理和更新 Mod 元数据  
2. 使用 `packwiz-install` 根据元数据下载对应的 Mod JAR 文件

该方式明确区分：

- 🧾 **定义（Metadata）**
- 📦 **实体文件（JAR Materialization）**

---

## 🧠 元数据辅助脚本

### `packwiz_to_metadata.py`

仓库中包含一个辅助脚本，用于 **从 packwiz 元数据中进一步生成高层 Mod 描述信息**，以辅助整理和归档。

### 🔍 功能说明

脚本将自动：

- 分析 `mods/*.pw.toml` 文件
- 判定 Mod 来源（Modrinth / CurseForge）
- 在可用情况下调用对应 API，获取：
  - 🏷️ 分类 / 标签
  - 🖥️ 客户端 / 服务端适用性

并生成一个 **“建议使用”的 YAML 文件**，供人工进一步整理。

---

### ▶️ 使用方式

#### 📴 离线模式（不联网）

```
python packwiz_to_metadata.py --repo packs/1.21.1-neoforge-v1 --offline
```

#### 🌐 联网模式

默认行为：

- Modrinth API：无需 Key
- CurseForge API：需要 Key

可通过以下两种方式之一提供 CurseForge API Key：

- **方式一：环境变量（推荐）**

```
CURSEFORGE_API_KEY=<你的_API_Key>
```

- **方式二：运行时参数**

```
python packwiz_to_metadata.py --repo packs/1.21.1-neoforge-v1 --curseforge-api-key <key>
```

---

### 📤 输出文件

默认输出路径：

```
<repo>/mod-metadata.generated.yml
```

示例：

```
packs/1.21.1-neoforge-v1/mod-metadata.generated.yml
```

该文件为 **自动生成结果**，仅作为参考输入，建议人工审阅后再整合为正式的 `mod-metadata.yml`。

---

## 📝 备注

- 脚本原名为 `modrinth_to_metadata.py`  
  已更名为 **`packwiz_to_metadata.py`**，以反映其多来源支持能力。
- 自动生成的元数据不应被视为最终权威结果。

---

## ⚖️ 使用与许可说明

本仓库用于 **个人或协作性质的整合包维护**。  
请遵循各个 Mod 自身的许可证与分发条款。
