---
name: bidding_info_search
description: 查询招标信息，通过关键词和省份筛选，获取招标标题和链接。
category: network
requires_confirmation: false
version: "1.0"
author: XuanShu Agent
tags: ["招标", "采购", "网络搜索"]
parameters:
  - name: keyword
    type: string
    description: 搜索关键词（必填），如：设备采购、工程建设
  - name: province
    type: string
    description: 省份（可选），如：北京、上海、广东、浙江
    default: ""
  - name: timeout
    type: integer
    description: 请求超时时间（秒），默认 15 秒
    default: 15
---

## Core Capability
访问 http://www.sizebid.com/bid-information.html 查询招标信息，使用 BeautifulSoup 解析数据。每个 class="row-info" 的 div 标签为一个项目，提取 class="publish-date" 的发布时间、以及 a 标签的标题和链接。

## Trigger Scenario
当需要查询招标信息、采购公告、项目招标时使用。

## Parameters
| Name     | Type    | Description                                         | Required | Default |
| -------- | ------- | --------------------------------------------------- | -------- | ------- |
| keyword  | string  | 搜索关键词（必填），如：设备采购、工程建设            | Yes      | -       |
| province | string  | 省份（可选），如：北京、上海、广东、浙江              | No       | ""      |
| timeout  | integer | 请求超时时间（秒），默认 30 秒                       | No       | 30      |

## Example Usage
```json
{
  "skill": "bidding_info_search",
  "args": {
    "keyword": "设备采购",
    "province": "北京"
  }
}
```

## Execution Signature
```python
def execute(keyword: str, province: str = "", timeout: int = 30, **kwargs) -> str:
    ...
```

## Output Format
```
✅ 招标信息查询成功
关键词: 设备采购
省份: 北京
共找到 X 条信息：

2026-05-10-招标标题 1：http://www.sizebid.com/...
2026-05-09-招标标题 2：http://www.sizebid.com/...
```

## Notes
- 使用 BeautifulSoup 解析 HTML，每个项目从 class="row-info" 的 div 中提取
- 发布时间为 class="publish-date" 的文本内容
- 自动处理相对路径，转换为完整 URL
- 结果长度超过 8000 字符时会自动截断
