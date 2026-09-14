import { UserContext } from './user_context';

export function filterUserContext(ctx: UserContext): boolean {
  const localFilterId = ctx.user_id;
  return localFilterId.length > 0 && ctx.roles.includes('admin');
}
