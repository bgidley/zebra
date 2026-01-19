import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Link, useSearchParams } from 'react-router-dom';
import { Plus, PlayCircle, Loader2, Trash2, X, Pause, Play } from 'lucide-react';
import {
  getProcesses,
  getDefinitions,
  startProcess,
  deleteProcess,
  pauseProcess,
  resumeProcess,
} from '../api/client';

export function ProcessesList() {
  const [searchParams] = useSearchParams();
  const [showStart, setShowStart] = useState(false);
  const [selectedDefinition, setSelectedDefinition] = useState('');
  const [properties, setProperties] = useState('{}');
  const queryClient = useQueryClient();

  const includeCompleted = searchParams.get('include_completed') === 'true';
  const stateFilter = searchParams.get('state') || undefined;

  const { data: processes, isLoading, error } = useQuery({
    queryKey: ['processes', { include_completed: includeCompleted, state: stateFilter }],
    queryFn: () => getProcesses({ include_completed: includeCompleted, state: stateFilter }),
  });

  const { data: definitions } = useQuery({
    queryKey: ['definitions'],
    queryFn: getDefinitions,
  });

  const startMutation = useMutation({
    mutationFn: startProcess,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['processes'] });
      setShowStart(false);
      setSelectedDefinition('');
      setProperties('{}');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteProcess,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['processes'] });
    },
  });

  const pauseMutation = useMutation({
    mutationFn: pauseProcess,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['processes'] });
    },
  });

  const resumeMutation = useMutation({
    mutationFn: resumeProcess,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['processes'] });
    },
  });

  const handleStart = () => {
    if (selectedDefinition) {
      try {
        const props = JSON.parse(properties);
        startMutation.mutate({
          definition_id: selectedDefinition,
          properties: props,
        });
      } catch {
        alert('Invalid JSON in properties');
      }
    }
  };

  const getStateColor = (state: string) => {
    switch (state) {
      case 'complete':
        return 'bg-green-900 text-green-300';
      case 'running':
        return 'bg-blue-900 text-blue-300';
      case 'paused':
        return 'bg-yellow-900 text-yellow-300';
      case 'failed':
        return 'bg-red-900 text-red-300';
      default:
        return 'bg-gray-700 text-gray-300';
    }
  };

  return (
    <div className="p-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-white">Processes</h1>
          <p className="text-gray-400 mt-1">Monitor and manage running workflows</p>
        </div>
        <button
          onClick={() => setShowStart(true)}
          className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors"
        >
          <Plus className="h-4 w-4" />
          Start Process
        </button>
      </div>

      {/* Filters */}
      <div className="flex gap-4 mb-6">
        <Link
          to="/processes"
          className={`px-3 py-1.5 rounded-lg text-sm ${
            !includeCompleted && !stateFilter
              ? 'bg-indigo-600 text-white'
              : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
          }`}
        >
          Active
        </Link>
        <Link
          to="/processes?include_completed=true"
          className={`px-3 py-1.5 rounded-lg text-sm ${
            includeCompleted
              ? 'bg-indigo-600 text-white'
              : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
          }`}
        >
          All
        </Link>
      </div>

      {/* Start Modal */}
      {showStart && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-gray-800 rounded-lg w-full max-w-md mx-4 border border-gray-700">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700">
              <h2 className="text-lg font-semibold text-white">Start Process</h2>
              <button
                onClick={() => setShowStart(false)}
                className="text-gray-400 hover:text-white"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="p-6 space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Definition
                </label>
                <select
                  value={selectedDefinition}
                  onChange={(e) => setSelectedDefinition(e.target.value)}
                  className="w-full bg-gray-900 border border-gray-700 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-indigo-500"
                >
                  <option value="">Select a definition...</option>
                  {definitions?.map((def) => (
                    <option key={def.id} value={def.id}>
                      {def.name} (v{def.version})
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Properties (JSON)
                </label>
                <textarea
                  value={properties}
                  onChange={(e) => setProperties(e.target.value)}
                  rows={5}
                  className="w-full bg-gray-900 border border-gray-700 rounded-lg px-4 py-3 text-white font-mono text-sm focus:outline-none focus:border-indigo-500"
                />
              </div>
              {startMutation.error && (
                <p className="text-sm text-red-400">
                  {(startMutation.error as Error).message}
                </p>
              )}
            </div>
            <div className="flex justify-end gap-3 px-6 py-4 border-t border-gray-700">
              <button
                onClick={() => setShowStart(false)}
                className="px-4 py-2 text-gray-300 hover:text-white"
              >
                Cancel
              </button>
              <button
                onClick={handleStart}
                disabled={startMutation.isPending || !selectedDefinition}
                className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {startMutation.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
                Start
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Content */}
      {isLoading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="h-8 w-8 animate-spin text-gray-500" />
        </div>
      ) : error ? (
        <div className="text-center py-12">
          <p className="text-red-400">{(error as Error).message}</p>
        </div>
      ) : processes?.length === 0 ? (
        <div className="text-center py-12">
          <PlayCircle className="h-12 w-12 text-gray-600 mx-auto mb-4" />
          <p className="text-gray-400">No processes found</p>
          <button
            onClick={() => setShowStart(true)}
            className="mt-4 text-indigo-400 hover:text-indigo-300"
          >
            Start your first process
          </button>
        </div>
      ) : (
        <div className="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
          <table className="w-full">
            <thead className="bg-gray-900">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase">
                  Definition
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase">
                  ID
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase">
                  State
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase">
                  Created
                </th>
                <th className="px-6 py-3 text-right text-xs font-medium text-gray-400 uppercase">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-700">
              {processes?.map((process) => (
                <tr key={process.id} className="hover:bg-gray-750">
                  <td className="px-6 py-4">
                    <Link
                      to={`/processes/${process.id}`}
                      className="text-white font-medium hover:text-indigo-400"
                    >
                      {process.definition_name}
                    </Link>
                  </td>
                  <td className="px-6 py-4">
                    <code className="text-sm text-gray-400">{process.id.slice(0, 8)}...</code>
                  </td>
                  <td className="px-6 py-4">
                    <span className={`px-2 py-1 text-xs font-medium rounded ${getStateColor(process.state)}`}>
                      {process.state}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-400">
                    {new Date(process.created_at).toLocaleString()}
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex justify-end gap-2">
                      {process.state === 'running' && (
                        <button
                          onClick={() => pauseMutation.mutate(process.id)}
                          className="p-1 text-yellow-400 hover:text-yellow-300"
                          title="Pause"
                        >
                          <Pause className="h-4 w-4" />
                        </button>
                      )}
                      {process.state === 'paused' && (
                        <button
                          onClick={() => resumeMutation.mutate(process.id)}
                          className="p-1 text-green-400 hover:text-green-300"
                          title="Resume"
                        >
                          <Play className="h-4 w-4" />
                        </button>
                      )}
                      <button
                        onClick={() => {
                          if (confirm('Delete this process?')) {
                            deleteMutation.mutate(process.id);
                          }
                        }}
                        className="p-1 text-red-400 hover:text-red-300"
                        title="Delete"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
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
