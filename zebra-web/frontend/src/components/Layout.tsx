import { Link, Outlet, useLocation } from 'react-router-dom';
import {
  LayoutDashboard,
  FileCode2,
  PlayCircle,
  ClipboardList,
  Settings,
  Activity,
} from 'lucide-react';

const navigation = [
  { name: 'Dashboard', href: '/', icon: LayoutDashboard },
  { name: 'Definitions', href: '/definitions', icon: FileCode2 },
  { name: 'Processes', href: '/processes', icon: PlayCircle },
  { name: 'Pending Tasks', href: '/tasks', icon: ClipboardList },
];

function classNames(...classes: string[]) {
  return classes.filter(Boolean).join(' ');
}

export function Layout() {
  const location = useLocation();

  return (
    <div className="min-h-screen bg-gray-900">
      {/* Sidebar */}
      <div className="fixed inset-y-0 left-0 w-64 bg-gray-800 border-r border-gray-700">
        {/* Logo */}
        <div className="flex items-center gap-2 h-16 px-6 border-b border-gray-700">
          <Activity className="h-8 w-8 text-indigo-500" />
          <span className="text-xl font-bold text-white">Zebra</span>
        </div>

        {/* Navigation */}
        <nav className="mt-6 px-3">
          <div className="space-y-1">
            {navigation.map((item) => {
              const isActive = location.pathname === item.href ||
                (item.href !== '/' && location.pathname.startsWith(item.href));
              return (
                <Link
                  key={item.name}
                  to={item.href}
                  className={classNames(
                    isActive
                      ? 'bg-gray-900 text-white'
                      : 'text-gray-300 hover:bg-gray-700 hover:text-white',
                    'group flex items-center gap-3 px-3 py-2 text-sm font-medium rounded-md'
                  )}
                >
                  <item.icon
                    className={classNames(
                      isActive ? 'text-indigo-400' : 'text-gray-400 group-hover:text-gray-300',
                      'h-5 w-5'
                    )}
                  />
                  {item.name}
                </Link>
              );
            })}
          </div>
        </nav>

        {/* Bottom section */}
        <div className="absolute bottom-0 left-0 right-0 p-4 border-t border-gray-700">
          <Link
            to="/settings"
            className="flex items-center gap-3 px-3 py-2 text-sm font-medium text-gray-300 hover:bg-gray-700 hover:text-white rounded-md"
          >
            <Settings className="h-5 w-5 text-gray-400" />
            Settings
          </Link>
        </div>
      </div>

      {/* Main content */}
      <div className="pl-64">
        <main className="min-h-screen">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
