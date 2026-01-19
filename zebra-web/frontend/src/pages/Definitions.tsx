import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { Plus, FileCode2, Loader2, Trash2, X } from 'lucide-react';
import { getDefinitions, createDefinition, deleteDefinition } from '../api/client';

export function DefinitionsList() {
  const [showCreate, setShowCreate] = useState(false);
  const [yamlContent, setYamlContent] = useState('');
  const queryClient = useQueryClient();

  const { data: definitions, isLoading, error } = useQuery({
    queryKey: ['definitions'],
    queryFn: getDefinitions,
  });

  const createMutation = useMutation({
    mutationFn: createDefinition,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['definitions'] });
      setShowCreate(false);
      setYamlContent('');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteDefinition,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['definitions'] });
    },
  });

  const handleCreate = () => {
    if (yamlContent.trim()) {
      createMutation.mutate({ yaml_content: yamlContent });
    }
  };

  return (
    <div className="p-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-white">Workflow Definitions</h1>
          <p className="text-gray-400 mt-1">Manage your workflow templates</p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors"
        >
          <Plus className="h-4 w-4" />
          New Definition
        </button>
      </div>

      {/* Create Modal */}
      {showCreate && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-gray-800 rounded-lg w-full max-w-2xl mx-4 border border-gray-700">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700">
              <h2 className="text-lg font-semibold text-white">Create Definition</h2>
              <button
                onClick={() => setShowCreate(false)}
                className="text-gray-400 hover:text-white"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="p-6">
              <label className="block text-sm font-medium text-gray-300 mb-2">
                YAML Content
              </label>
              <textarea
                value={yamlContent}
                onChange={(e) => setYamlContent(e.target.value)}
                rows={15}
                className="w-full bg-gray-900 border border-gray-700 rounded-lg px-4 py-3 text-white font-mono text-sm focus:outline-none focus:border-indigo-500"
                placeholder="# Paste your workflow YAML here..."
              />
              {createMutation.error && (
                <p className="mt-2 text-sm text-red-400">
                  {(createMutation.error as Error).message}
                </p>
              )}
            </div>
            <div className="flex justify-end gap-3 px-6 py-4 border-t border-gray-700">
              <button
                onClick={() => setShowCreate(false)}
                className="px-4 py-2 text-gray-300 hover:text-white"
              >
                Cancel
              </button>
              <button
                onClick={handleCreate}
                disabled={createMutation.isPending || !yamlContent.trim()}
                className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {createMutation.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
                Create
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
      ) : definitions?.length === 0 ? (
        <div className="text-center py-12">
          <FileCode2 className="h-12 w-12 text-gray-600 mx-auto mb-4" />
          <p className="text-gray-400">No definitions yet</p>
          <button
            onClick={() => setShowCreate(true)}
            className="mt-4 text-indigo-400 hover:text-indigo-300"
          >
            Create your first definition
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {definitions?.map((def) => (
            <div
              key={def.id}
              className="bg-gray-800 rounded-lg border border-gray-700 hover:border-gray-600 transition-colors"
            >
              <Link to={`/definitions/${def.id}`} className="block p-6">
                <div className="flex items-start justify-between">
                  <div>
                    <h3 className="text-lg font-semibold text-white">{def.name}</h3>
                    <p className="text-sm text-gray-400 mt-1">Version {def.version}</p>
                  </div>
                  <div className="flex items-center gap-1 px-2 py-1 bg-gray-700 rounded text-xs text-gray-300">
                    {def.task_count} tasks
                  </div>
                </div>
                {def.description && (
                  <p className="text-gray-400 text-sm mt-3 line-clamp-2">{def.description}</p>
                )}
                <p className="text-xs text-gray-500 mt-3 font-mono">{def.id}</p>
              </Link>
              <div className="border-t border-gray-700 px-6 py-3 flex justify-end">
                <button
                  onClick={(e) => {
                    e.preventDefault();
                    if (confirm('Delete this definition?')) {
                      deleteMutation.mutate(def.id);
                    }
                  }}
                  className="text-red-400 hover:text-red-300"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
