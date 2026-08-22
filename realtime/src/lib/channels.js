/**
 * Channel naming and subscription rules.
 *
 * Mirrors `backend/core/realtime.py` - if a name changes there it must change
 * here, otherwise Django publishes into a channel nobody is listening on.
 *
 *   user:<userId>                  one person, all their open tabs
 *   org:<orgId>                    everyone in the organization
 *   org:<orgId>:panel:<panel>      one panel (admin | user) of one org
 *   org:<orgId>:role:<role>        one role within an org
 *   broadcast                      every connected client
 */
export const BROADCAST = 'broadcast';

export const ADMIN_ROLES = ['super_admin', 'admin', 'hr', 'manager'];

export const userChannel = (userId) => `user:${userId}`;
export const orgChannel = (orgId) => `org:${orgId}`;
export const panelChannel = (orgId, panel) => `org:${orgId}:panel:${panel}`;
export const roleChannel = (orgId, role) => `org:${orgId}:role:${role}`;

export const panelForRole = (role) => (ADMIN_ROLES.includes(role) ? 'admin' : 'user');

/**
 * Channels a client is subscribed to the moment it connects, derived from its
 * token claims. The client never has to ask for these.
 */
export function defaultChannelsFor(identity) {
  const channels = [userChannel(identity.userId), BROADCAST];
  if (identity.orgId) {
    channels.push(orgChannel(identity.orgId));
    channels.push(panelChannel(identity.orgId, panelForRole(identity.role)));
    channels.push(roleChannel(identity.orgId, identity.role));
  }
  return [...new Set(channels)];
}

/**
 * Authorisation for an explicit `subscribe` request.
 *
 * A client may only ever reach its own user channel and channels inside its own
 * organization, and only admin-panel roles may join an admin channel. This is
 * what stops a browser from subscribing to another tenant's stream.
 */
export function canSubscribe(identity, channel) {
  if (typeof channel !== 'string' || !channel.length || channel.length > 200) return false;
  if (channel === BROADCAST) return true;

  if (channel.startsWith('user:')) {
    return channel === userChannel(identity.userId);
  }

  if (channel.startsWith('org:')) {
    if (!identity.orgId) return false;
    const [, orgId, kind, value] = channel.split(':');
    if (orgId !== String(identity.orgId)) return false;
    if (!kind) return true;                                   // org:<id>
    if (kind === 'panel') {
      return value === 'user' || ADMIN_ROLES.includes(identity.role);
    }
    if (kind === 'role') {
      return value === identity.role || ADMIN_ROLES.includes(identity.role);
    }
    return false;
  }

  return false;
}

export function filterAllowed(identity, channels) {
  const allowed = [];
  const rejected = [];
  for (const channel of channels ?? []) {
    (canSubscribe(identity, channel) ? allowed : rejected).push(channel);
  }
  return { allowed, rejected };
}
