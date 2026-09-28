# 图元与设计资产目录 (Assets)

本目录存放 DAUG 项目的核心架构图、数据模型图、更新生命周期图以及宣讲概念图。

## 目录结构

```text
assets/
├── data-model.svg / .png             # 数据模型与实体关系高清图 (4000x2150)
├── system-architecture.svg / .png    # 系统总体架构与分层设计高清图 (4000x2050)
├── update-lifecycle.svg / .png       # 变更到补丁的更新生命周期状态机高清图 (4000x1800)
├── explainer/                        # 概念讲解与宣讲海报
│   ├── daug-project-explainer.png            # 英文概念讲解海报
│   ├── daug-project-explainer-zh.png         # 中文概念讲解海报 (标准版)
│   ├── daug-project-explainer-chinese.png    # 中文概念讲解海报 (备用版)
│   ├── project_explainer.jpg                 # 高清宽幅英文讲解图
│   └── project_explainer_cn.jpg              # 高清宽幅中文讲解图
└── README.md
```

## 规范要求

1. 根目录仅保留当前正式技术方案与文档直接引用的高清技术图纸（提供 SVG 矢量源文件与 PNG 渲染文件）。
2. 宣传展示、演示幻灯片及概念海报等非核心工程图纸统一定位于 `explainer/` 目录。
