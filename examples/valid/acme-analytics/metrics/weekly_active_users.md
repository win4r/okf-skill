---
type: Metric
title: Weekly Active Users
description: Distinct purchasing users per ISO week.
tags: [engagement, kpi]
timestamp: 2026-05-28T14:30:00Z
---
# Overview

Distinct `customer_id`s from [Orders](/tables/orders.md) that completed at least one order
within an ISO week.

# Definition

```sql
SELECT EXTRACT(ISOWEEK FROM created_at) AS week, COUNT(DISTINCT customer_id) AS wau
FROM `acme.sales.orders`
GROUP BY week;
```
