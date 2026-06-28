---
type: Playbook
title: Revenue Reconciliation
description: How to reconcile warehouse gross revenue with the finance ledger.
tags: [finance, runbook, revenue]
timestamp: 2026-05-28T14:30:00Z
---
# Overview

This playbook reconciles [Gross Revenue](/metrics/gross_revenue.md) computed from
[Orders](/tables/orders.md) against the finance ledger. It is an abstract concept and has
no single `resource` URI.

# Steps

1. Compute warehouse gross revenue for the period from [Orders](/tables/orders.md).
2. Pull the finance ledger total for the same period.
3. Investigate any delta over 0.5% using [Order Items](/tables/order_items.md).

# Citations

[1] [Month-end close calendar](https://acme.example/docs/close-calendar)
