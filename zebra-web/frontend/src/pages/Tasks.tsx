import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { ClipboardList, Loader2 } from 'lucide-react';
import { getPendingTasks } from '../api/client';

export function TasksList() {
  const { data: tasks, isLoading, error } = useQuery({
    queryKey: ['pendingTasks'],
    queryFn: getPendingTasks,
    refetchInterval: 5000, // Poll every 5 seconds for new tasks
  });

  return (
    <div className="p-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-white">Pending Tasks</h1>
        <p className="text-gray-400 mt-1">Tasks waiting for user input</p>
      </div>

      {/* Content */}
      {isLoading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="h-8 w-8 animate-spin text-gray-500" />
        </div>
      ) : error ? (
        <div className="text-center py-12">
          <p className="text-red-400">{(error as Error).message}</p>
        </div>
      ) : tasks?.length === 0 ? (
        <div className="text-center py-12">
          <ClipboardList className="h-12 w-12 text-gray-600 mx-auto mb-4" />
          <p className="text-gray-400">No pending tasks</p>
          <p className="text-gray-500 text-sm mt-2">
            Tasks waiting for user input will appear here
          </p>
        </div>
      ) : (
        <div className="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
          <table className="w-full">
            <thead className="bg-gray-900">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase">
                  Task
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase">
                  Workflow
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase">
                  Process
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase">
                  Created
                </th>
                <th className="px-6 py-3 text-right text-xs font-medium text-gray-400 uppercase">
                  Action
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-700">
              {tasks?.map((task) => (
                <tr key={task.id} className="hover:bg-gray-750">
                  <td className="px-6 py-4">
                    <span className="text-white font-medium">
                      {task.task_definition_name || task.task_definition_id}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-gray-400">
                    {task.process_definition_name || '-'}
                  </td>
                  <td className="px-6 py-4">
                    <Link
                      to={`/processes/${task.process_id}`}
                      className="text-sm text-indigo-400 hover:text-indigo-300 font-mono"
                    >
                      {task.process_id.slice(0, 8)}...
                    </Link>
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-400">
                    {new Date(task.created_at).toLocaleString()}
                  </td>
                  <td className="px-6 py-4 text-right">
                    <Link
                      to={`/tasks/${task.id}`}
                      className="px-3 py-1.5 bg-indigo-600 text-white text-sm rounded hover:bg-indigo-700"
                    >
                      Complete
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
