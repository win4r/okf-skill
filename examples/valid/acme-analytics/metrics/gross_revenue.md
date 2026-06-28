---
type: Metric
title: Gross Revenue
description: Sum of completed order totals over a period.
tags: [revenue, finance, kpi]
timestamp: 2026-05-28T14:30:00Z
---
# Overview

Gross revenue is the sum of `order_total` from [Orders](/tables/orders.md) over a period,
before refunds. See [Revenue Reconciliation](/playbooks/revenue_reconciliation.md) for how
this is squared with finance.

# Definition

```sql
SELECT DATE_TRUNC(created_at, MONTH) AS month, SUM(order_total) AS gross_revenue
FROM `acme.sales.orders`
GROUP BY month;
```

# Citations

[1] [Finance metric definitions](https://acme.example/docs/finance-metrics)
