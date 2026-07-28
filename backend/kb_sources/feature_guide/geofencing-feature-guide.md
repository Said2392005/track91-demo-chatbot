---
doc_id: geofencing-feature-guide
title: Geofencing Feature Guide
category: feature_guide
version: v1
approved_pricing: false
---

## What is Geofencing

Geofencing lets you draw a virtual boundary — around a warehouse, delivery zone, or restricted
area — on the map, and have Track91 automatically detect when a vehicle enters or exits that
boundary. Geofences are defined per company and can be applied to specific vehicles or to an
entire fleet group.

## How Geofence Alerts Work

When a vehicle assigned to a geofence crosses its boundary, Track91 generates a
`geofence_entry` or `geofence_exit` alert with the vehicle, timestamp, and the geofence name.
These alerts appear alongside other alert types (speeding, low fuel, etc.) in the Alerts
dashboard and can be filtered by geofence.

## Creating a Geofence (UI walkthrough)

From the web dashboard, go to **Fleet > Geofences > New Geofence**, draw a shape on the map
(polygon or circle), give it a name, and choose which vehicles or fleet groups it applies to.
Creating and editing geofences through the chat assistant is not yet supported — use the web
dashboard for now.

## Best Practices

Keep geofence boundaries slightly larger than the physical site they represent to avoid false
exit alerts from GPS drift near the edge. Name geofences descriptively (e.g. "Pune Warehouse —
Loading Dock") rather than generically ("Zone 1"), since geofence names appear directly in
alert notifications and reports.
