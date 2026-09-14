# Authentication Context Design

## Overview
The authentication service constructs a `UserContext` object for every incoming request.

## Data Structure
The `UserContext` interface exposes the following primary fields:
- `user_id`: The unique system-wide identifier of the authenticated user.
- `tenant_id`: The organisation / tenant identifier.
- `roles`: List of RBAC roles assigned to this identity.

When downstream services validate authorization, they must extract `user_id` to look up permissions.
