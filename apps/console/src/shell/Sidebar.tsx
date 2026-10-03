import { NavLink } from 'react-router-dom';
import { useAuth } from '../auth/context';
import { ConsoleIcon, type ConsoleIconName } from './ConsoleIcon';

interface NavItem {
  to: string;
  label: string;
  icon: ConsoleIconName;
  /** Roles allowed to see the item; undefined means every staff role. */
  roles?: string[];
}

const ITEMS: NavItem[] = [
  { to: '/providers', label: 'Providers', icon: 'home' },
  { to: '/schema', label: 'Schema review', icon: 'documents' },
  { to: '/health', label: 'Health & quarantine', icon: 'health' },
  {
    to: '/audit',
    label: 'Audit',
    icon: 'audit',
    roles: ['compliance_privacy_officer', 'administrator'],
  },
];

export function Sidebar({ collapsed }: { collapsed: boolean }): JSX.Element {
  const { staff } = useAuth();
  const items = ITEMS.filter(
    (item) => !item.roles || (staff && item.roles.includes(staff.role)),
  );
  return (
    <nav
      className={`sidebar${collapsed ? ' sidebar-collapsed' : ''}`}
      aria-label="Console sections"
    >
      <ul className="sidebar-list">
        {items.map((item) => (
          <li key={item.to}>
            <NavLink
              to={item.to}
              className="sidebar-item"
              title={collapsed ? item.label : undefined}
            >
              <ConsoleIcon name={item.icon} className="sidebar-item-icon" />
              {collapsed ? (
                <span className="visually-hidden">{item.label}</span>
              ) : (
                <span className="sidebar-item-label">{item.label}</span>
              )}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}
