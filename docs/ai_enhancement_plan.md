# AI Enhancement Plan

更新日期：2026-05-31

## 目标

在 15 分钟整盘总思考时间内，提高六子棋 AI 的落子质量和时间利用效率。AI 必须始终遵守整盘总时限，并把更多时间投入到高风险、高收益局面。

当前项目已经完成第一轮 AI 增强框架，下一阶段重点不再是继续堆叠搜索功能，而是建立更强的可度量评估体系，并在评估保护下逐步增强搜索、排序和评估函数。

## 当前状态

### 已完成能力

- 整盘总时间控制：
  - `GameConfig.ai_think_time_seconds` 作为整盘总预算使用，默认 900 秒。
  - `GamePage` 维护 AI 剩余时间并显示倒计时。
  - AI 时间耗尽时判为平局。
  - `ai/time_control.py` 将整盘剩余时间转换为单回合预算。
- 战术紧迫度：
  - `AlphaBeltaMaxAI.estimate_urgency(board, color, count)` 已实现。
  - 紧迫度覆盖直接胜、必须防守、多威胁、强制链和复杂候选局面。
  - `GamePage` 已优先使用 AI 自身的紧迫度估计；不支持该接口的 AI 回退到空位数规则。
- `AlphaBeltaMaxAI` 搜索增强：
  - alpha-beta / negamax。
  - PVS 风格窗口搜索。
  - 迭代加深。
  - history score。
  - killer pair。
  - root hint pair。
  - 轻量 threat quiescence。
  - 统一 pair 排序评分。
  - 置换表 key 和 replacement policy。
  - 攻防形状、跳连和夹点评估加分。
  - `last_decision` 和 `last_search_stats` 决策统计。
- 评估工具：
  - 固定局面集 `tests/fixtures/ai_positions/`。
  - 固定局面加载和评测 `ai/evaluation.py`。
  - 固定局面 benchmark `scripts/benchmark_ai.py`，支持 JSON/CSV。
  - self-play 评测 `scripts/self_play_ai.py`，支持 paired 换边对局。

### 当前基线

最新已知验证命令：

```bash
python -m unittest tests.test_alpha_belta_max_ai tests.test_alpha_belta_plus_ai
python scripts/benchmark_ai.py tests/fixtures/ai_positions --engine alpha_belta_max --format json
python -m unittest tests.test_ai_self_play tests.test_ai_position_suite tests.test_ai_time_control tests.test_turn_timer
python -m unittest tests.test_ai_factory tests.test_ai_config_page
```

最新已知结果：

```text
max/plus AI tests: 47 passed
fixed-position benchmark: 6/6 passed, pass_rate=1.0
evaluation/self-play/timer tests: 20 passed
factory/config tests: 10 passed
```

## 当前风险

1. 固定局面数量仍偏少，只有 6 个，无法稳定判断 threat search、排序和评估函数改动是否真的增强。
2. self-play CSV 输出缺少剩余时间、超时和搜索统计细节，不利于区分“棋力增强”和“耗时增加”。
3. 还缺少版本对比脚本，benchmark 结果需要人工比较。
4. threat quiescence 当前是低风险第一版，继续加深前必须先补充局面覆盖和节点统计。
5. pair 排序已经增强，但候选生成仍存在“生成全部 pair 后排序”的潜在性能瓶颈。
6. 低时间模式目前主要依赖单步预算变小，搜索内部还没有按剩余时间主动降级。

## 下一轮执行顺序

### P0：收口评估基础设施

优先完成这些改动，因为它们能让后续所有 AI 改动更容易判断强弱。

- [x] 扩展 `scripts/self_play_ai.py` 的 CSV 输出字段：
  - `black_remaining_seconds`
  - `white_remaining_seconds`
  - 后续可继续加入平均每步耗时、平均深度和平均节点数。
- [x] 新增 `scripts/compare_ai_versions.py`：
  - 比较两个固定局面 benchmark JSON。
  - 输出通过率变化、平均耗时变化、平均节点数变化、平均完成深度变化。
  - 当新版本通过率下降时返回非零退出码。
- [x] 固化对比测试：
  - `tests/test_ai_self_play.py` 覆盖 self-play CSV 新字段。
  - 新增 `tests/test_compare_ai_versions.py` 覆盖版本对比逻辑和 CLI。

### P1：扩展固定局面集

在继续增强搜索前，把固定局面从 6 个扩展到至少 20 个。

当前状态：

- [x] 第一批固定局面已扩展到 20 个。
- [x] 已增加四个方向的直接取胜局面。
- [x] 已增加四个方向的开放五连双端防守局面。
- [x] 已增加横向、纵向和斜向断点取胜/防守局面。
- [x] `tests.test_ai_position_suite` 已增加最少 20 个局面的数量门槛。
- [ ] 后续继续补充更复杂的反先、低时间和中盘复杂候选局面。

优先补充类型：

- [ ] 连续强制进攻。
- [ ] 连续强制防守。
- [x] 双威胁制造。
- [x] 双威胁阻断。
- [ ] 对手反先威胁。
- [ ] 低时间模式必须返回合法落子。
- [ ] 看似能进攻但实际必须防守的局面。
- [ ] 开局布局选择。
- [ ] 中盘候选很多的复杂局面。
- [x] 残局直接胜负局面。

判定标准：

- 新版本固定局面总通过率不能低于旧版本。
- 核心战术局面通过率必须高于旧版本或保持 100%。
- 低时间局面必须始终返回合法落子。

### P2：继续增强 threat quiescence

当前 threat quiescence 最大延伸深度为 1。下一步应谨慎扩展：

- 将最大延伸深度做成可配置。
- 只在高紧迫度局面启用更深延伸。
- 把强制威胁链纳入 quiescence。
- 记录 quiescence 节点数，用于判断耗时成本。
- deadline 剩余不足时直接回退静态评估。

禁止在没有新增固定局面和耗时统计前直接放开全量 threat search。

### P3：优化候选生成和 pair 排序

当前 `_pair_order_score()` 已能让直接胜和必须防守覆盖 root hint/history。下一步重点是减少无效 pair：

- 先用单点评分筛选 top-K 候选点。
- 战术关键点强制保留，不受 top-K 限制。
- 只从 top-K 中生成高价值 pair。
- root 层 K 大一些，内部节点 K 小一些。
- 增加测试，确保直接胜、必须防守、多威胁制造和强制链阻断不会被 top-K 过滤。

### P4：真正实现低时间搜索降级

当前低时间模式主要通过 `allocate_ai_move_time()` 获得更小预算。后续应让搜索内部主动降级：

- 剩余总时间低于 30 秒时跳过高成本强制链搜索。
- 剩余总时间低于 5 秒时只做直接胜、必须防守和静态排序。
- 任意 deadline 边界都必须保留最后一个合法 best pair。
- self-play 报告中记录低时间触发次数和超时次数。

### P5：评估函数结构化

`_cell_val()` 已有攻防形状和跳连加分。下一步不要继续堆散乱 bonus，而是拆分结构化分数：

- `attack_score`
- `defense_score`
- `shape_score`
- `phase_score`
- `tactical_override`

然后按阶段调权重：

- 开局重布局和中心控制。
- 中盘重威胁制造。
- 残局重直接胜负和强制链。

## 合入标准

每次 AI 行为改动至少满足：

```bash
python -m unittest tests.test_ai_time_control
python -m unittest tests.test_alpha_belta_plus_ai
python -m unittest tests.test_alpha_belta_max_ai
python -m unittest tests.test_ai_factory
python -m unittest tests.test_turn_timer
python -m unittest tests.test_ai_position_suite
```

涉及 self-play 或 benchmark 脚本时额外运行：

```bash
python -m unittest tests.test_ai_self_play
python scripts/benchmark_ai.py tests/fixtures/ai_positions --engine alpha_belta_max --format json
```

发布或大改前运行：

```bash
python -m unittest discover tests
```

判断 AI 是否增强时同时看：

- 固定局面通过率。
- paired self-play 胜率。
- 平均耗时。
- 平均搜索深度。
- 平均节点数。
- 超时次数。
- 低时间模式合法落子率。

如果胜率提升但超时或耗时显著增加，应先修时间管理，不能直接合入。
