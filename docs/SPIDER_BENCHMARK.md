# Spider 基准测试

SQLPilot采用两阶段基准：Spider 1.0用于基础跨域Text-to-SQL回归，Spider 2.0用于后续企业级工作流压力测试。标准基准不能替代医保业务Golden Set，两者分开报告。

## 数据目录

官方评测代码位于`data/benchmarks/spider-official`。Spider Git仓库不包含数据库文件，需要从Spider官网下载数据包，并将`database/<db_id>/<db_id>.sqlite`复制到该目录下。

## 命令

检查数据是否齐备，并导出开发集任务：

```powershell
python tools/spider_benchmark.py --export-cases data/benchmarks/work/spider-dev.jsonl
```

预测文件使用JSONL，每行包含`case_id`和`sql`：

```json
{"case_id":"dev-0000","sql":"SELECT count(*) FROM singer"}
```

计算执行准确率：

```powershell
python tools/spider_benchmark.py --predictions data/benchmarks/work/predictions.jsonl
```

使用标准SQL验证评测器和数据库完整性（预期EX为100%）：

```powershell
python tools/spider_benchmark.py --dataset data/benchmarks/spider-data/spider_data --oracle-smoke
```

报告写入`data/benchmarks/reports/spider-dev.json`，包含总体EX、缺失预测、数据库缺失、执行错误、结果不一致以及按难度分组统计。

## 公布口径

- `Spider EX`：所有可执行样本的结果一致率。
- `Coverage`：系统产生有效预测的样本比例。
- `Safe refusal`：能力边界外问题被明确拒绝的比例。
- `Healthcare Golden EX`：医保权威对账集结果一致率。

不要把“SQL成功执行率”当成“结果正确率”，也不要用Spider成绩替代客户数据库上的业务验收。
