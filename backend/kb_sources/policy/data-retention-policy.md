---
doc_id: data-retention-policy
title: Data Retention Policy
category: policy
version: v1
approved_pricing: false
---

## Overview

This policy describes how long Track91 retains different categories of fleet data, and what
happens to your data if your account is cancelled. It does not cover live GPS telemetry
(current location, speed, fuel, live health), which is never stored by Track91 — it is only
relayed to your dashboard in real time and discarded immediately after delivery.

## Trip & Location History Retention

Completed trip records (start/end time, locations, distance, duration) are retained for 12
months from the trip's end date, after which they are automatically purged. Raw, second-by-
second location pings are not retained at all — only the summarized trip record is kept.

## Alert & Maintenance History Retention

Alert records (speeding, geofence, panic, low fuel, and similar events) and maintenance service
records are retained for 24 months, since these are commonly referenced for compliance audits
and vehicle resale history well after the fact.

## Chat Conversation Retention

Chatbot conversation transcripts are retained for 6 months to support quality review and
troubleshooting of the assistant itself, after which they are permanently deleted. Any vehicle
or driver data referenced within a conversation follows that data's own retention period above
— deleting the conversation transcript does not delete the underlying trip/alert/maintenance
records it referenced.

## Data Deletion Requests

If your company cancels its Track91 subscription, all data is retained for 30 days in case of
reactivation, then permanently deleted. You may request earlier deletion by contacting support;
earlier deletion is irreversible and cannot be undone once processed.
