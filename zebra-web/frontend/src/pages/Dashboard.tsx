import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { FileCode2, PlayCircle, ClipboardList, CheckCircle2, AlertCircle, Loader2 } from 'lucide-react';
import { getDefinitions, getProcesses, getPendingTasks, getHealth } from '../api/client';

function StatCard({
  title,
  value,
  icon: Icon,
  href,
  color,
  isLoading,
}: {
  title: string;
  value: number;
  icon: React.ElementType;
  href: string;
  color: string;
  isLoading: boolean;
}) {
  return (
    <Link
      to={href}
      className="bg-gray-800 rounded-lg p-6 hover:bg-gray-750 transition-colors border border-gray-700"
    >
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-gray-400">{title}</p>
          <p className="text-3xl font-bold text-white mt-1">
            {isLoading ? <Loader2 className="h-8 w-8 animate-spin text-gray-500" /> : value}
          </p>
        </div>
        <div className={`p-3 rounded-lg ${color}`}>
          <Icon className="h-6 w-6 text-white" />
        </div>
      </div>
    </Link>
  );
}

export function Dashboard() {
  const healthQuery = useQuery({
    queryKey: ['health'],
    queryFn: getHealth,
    refetchInterval: 30000,
  });

  const definitionsQuery = useQuery({
    queryKey: ['definitions'],
    queryFn: getDefinitions,
  });

  const processesQuery = useQuery({
    queryKey: ['processes', { include_completed: true }],
    queryFn: () => getProcesses({ include_completed: true }),
  });

  const pendingTasksQuery = useQuery({
    queryKey: ['pendingTasks'],
    queryFn: getPendingTasks,
  });

  const definitions = definitionsQuery.data || [];
  const processes = processesQuery.data || [];
  const pendingTasks = pendingTasksQuery.data || [];

  const runningProcesses = processes.filter((p) => p.state === 'running').length;
  const completedProcesses = processes.filter((p) => p.state === 'complete').length;

  return (
    <div className="p-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-white">Dashboard</h1>
        <p className="text-gray-400 mt-1">Overview of your workflow system</p>
      </div>

      {/* Health Status */}
      <div className="mb-8">
        <div className="flex items-center gap-3">
          {healthQuery.isLoading ? (
            <Loader2 className="h-5 w-5 animate-spin text-gray-500" />
          ) : healthQuery.data?.status === 'healthy' ? (
            <>
              <CheckCircle2 className="h-5 w-5 text-green-500" />
              <span className="text-green-400">System healthy</span>
            </>
          ) : (
            <>
              <AlertCircle className="h-5 w-5 text-red-500" />
              <span className="text-red-400">System unhealthy</span>
            </>
          )}
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        <StatCard
          title="Definitions"
          value={definitions.length}
          icon={FileCode2}
          href="/definitions"
          color="bg-indigo-600"
          isLoading={definitionsQuery.isLoading}
        />
        <StatCard
          title="Running Processes"
          value={runningProcesses}
          icon={PlayCircle}
          href="/processes?state=running"
          color="bg-blue-600"
          isLoading={processesQuery.isLoading}
        />
        <StatCard
          title="Completed"
          value={completedProcesses}
          icon={CheckCircle2}
          href="/processes?include_completed=true"
          color="bg-green-600"
          isLoading={processesQuery.isLoading}
        />
        <StatCard
          title="Pending Tasks"
          value={pendingTasks.length}
          icon={ClipboardList}
          href="/tasks"
          color="bg-amber-600"
          isLoading={pendingTasksQuery.isLoading}
        />
      </div>

      {/* Recent Activity */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recent Processes */}
        <div className="bg-gray-800 rounded-lg border border-gray-700">
          <div className="px-6 py-4 border-b border-gray-700">
            <h2 className="text-lg font-semibold text-white">Recent Processes</h2>
          </div>
          <div className="divide-y divide-gray-700">
            {processesQuery.isLoading ? (
              <div className="p-6 text-center">
                <Loader2 className="h-6 w-6 animate-spin text-gray-500 mx-auto" />
              </div>
            ) : processes.length === 0 ? (
              <div className="p-6 text-center text-gray-500">No processes yet</div>
            ) : (
              processes.slice(0, 5).map((process) => (
                <Link
                  key={process.id}
                  to={`/processes/${process.id}`}
                  className="flex items-center justify-between px-6 py-4 hover:bg-gray-750"
                >
                  <div>
                    <p className="text-white font-medium">{process.definition_name}</p>
                    <p className="text-sm text-gray-400">{process.id.slice(0, 8)}...</p>
                  </div>
                  <span
                    className={`px-2 py-1 text-xs font-medium rounded ${
                      process.state === 'complete'
                        ? 'bg-green-900 text-green-300'
                        : process.state === 'running'
                          ? 'bg-blue-900 text-blue-300'
                          : process.state === 'failed'
                            ? 'bg-red-900 text-red-300'
                            : 'bg-gray-700 text-gray-300'
                    }`}
                  >
                    {process.state}
                  </span>
                </Link>
              ))
            )}
          </div>
          {processes.length > 5 && (
            <div className="px-6 py-3 border-t border-gray-700">
              <Link to="/processes" className="text-sm text-indigo-400 hover:text-indigo-300">
                View all processes
              </Link>
            </div>
          )}
        </div>

        {/* Pending Tasks */}
        <div className="bg-gray-800 rounded-lg border border-gray-700">
          <div className="px-6 py-4 border-b border-gray-700">
            <h2 className="text-lg font-semibold text-white">Pending Tasks</h2>
          </div>
          <div className="divide-y divide-gray-700">
            {pendingTasksQuery.isLoading ? (
              <div className="p-6 text-center">
                <Loader2 className="h-6 w-6 animate-spin text-gray-500 mx-auto" />
              </div>
            ) : pendingTasks.length === 0 ? (
              <div className="p-6 text-center text-gray-500">No pending tasks</div>
            ) : (
              pendingTasks.slice(0, 5).map((task) => (
                <Link
                  key={task.id}
                  to={`/tasks/${task.id}`}
                  className="flex items-center justify-between px-6 py-4 hover:bg-gray-750"
                >
                  <div>
                    <p className="text-white font-medium">
                      {task.task_definition_name || task.task_definition_id}
                    </p>
                    <p className="text-sm text-gray-400">
                      {task.process_definition_name || task.process_id.slice(0, 8)}
                    </p>
                  </div>
                  <span className="px-2 py-1 text-xs font-medium rounded bg-amber-900 text-amber-300">
                    waiting
                  </span>
                </Link>
              ))
            )}
          </div>
          {pendingTasks.length > 5 && (
            <div className="px-6 py-3 border-t border-gray-700">
              <Link to="/tasks" className="text-sm text-indigo-400 hover:text-indigo-300">
                View all tasks
              </Link>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
