export interface UserContext {
  user_id: string;
  tenant_id: string;
  roles: string[];
  authenticated_at: string;
}

export function createUserContext(userId: string, tenantId: string, roles: string[] = []): UserContext {
  return {
    user_id: userId,
    tenant_id: tenantId,
    roles,
    authenticated_at: new Date().toISOString()
  };
}
