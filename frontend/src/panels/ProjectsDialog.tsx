import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '@/api/client'
import { Button, Dialog } from '@/components/ui/controls'
import { useT } from '@/i18n'
import { useSceneStore } from '@/state/sceneStore'
import { sanitizeView, useViewStore } from '@/state/viewStore'

export function ProjectsDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const { t, lang } = useT()
  const client = useQueryClient()
  const projectId = useSceneStore((s) => s.projectId)
  const projectName = useSceneStore((s) => s.projectName)
  const [name, setName] = useState('')
  const effectiveName = name || projectName
  const list = useQuery({ queryKey: ['projects'], queryFn: api.projects, enabled: open, retry: false })
  const refresh = () => client.invalidateQueries({ queryKey: ['projects'] })
  const save = useMutation({
    mutationFn: (asNew: boolean) =>
      api.saveProject(effectiveName.trim(), useSceneStore.getState().scene, { ...useViewStore.getState().settings() }, asNew ? undefined : (projectId ?? undefined)),
    onSuccess: (p) => {
      useSceneStore.setState({ projectId: p.id, projectName: p.name })
      setName('')
      void refresh()
    },
  })
  const load = useMutation({
    mutationFn: api.project,
    onSuccess: (p) => {
      useSceneStore.getState().load(p.scene, { projectId: p.id, name: p.name })
      useViewStore.getState().set({ ...sanitizeView(p.view), probePoint: null })
      onOpenChange(false)
    },
  })
  const remove = useMutation({
    mutationFn: api.deleteProject,
    onSuccess: (_d, id) => {
      if (id === projectId) useSceneStore.setState({ projectId: null, projectName: '' })
      void refresh()
    },
  })
  const error = list.error ?? save.error ?? load.error ?? remove.error
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title={t('projects.title')} closeLabel={t('common.close')}>
      <div className="flex flex-col gap-3">
        <div className="flex items-center gap-2">
          <input
            aria-label={t('projects.name')}
            placeholder={t('projects.name')}
            value={effectiveName}
            onChange={(e) => setName(e.target.value)}
            className="h-8 flex-1 rounded-md border border-border bg-bg px-2 text-sm"
          />
          {projectId && (
            <Button variant="primary" size="md" disabled={!effectiveName.trim() || save.isPending} onClick={() => save.mutate(false)}>
              {t('projects.save')}
            </Button>
          )}
          <Button variant={projectId ? 'default' : 'primary'} size="md" disabled={!effectiveName.trim() || save.isPending} onClick={() => save.mutate(true)}>
            {t(projectId ? 'projects.saveAsNew' : 'projects.save')}
          </Button>
        </div>
        {error && <p role="alert" className="rounded-md border border-danger/40 bg-danger/10 p-2 text-xs text-danger">{t('projects.error')}: {error.message}</p>}
        <div>
          <h4 className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-muted">{t('projects.saved')}</h4>
          {list.isLoading && <p className="text-xs text-muted">{t('common.loading')}</p>}
          {list.data?.length === 0 && <p className="text-xs text-muted">{t('projects.empty')}</p>}
          <ul className="flex flex-col gap-1">
            {list.data?.map((p) => (
              <li key={p.id} className="flex items-center gap-2 rounded-md border border-border bg-panel-2/60 px-2 py-1.5 text-xs">
                <span className="flex-1 truncate font-medium">{p.name}</span>
                <span className="text-[11px] text-muted">{new Date(p.updated_at).toLocaleString(lang)}</span>
                <Button onClick={() => load.mutate(p.id)}>{t('projects.load')}</Button>
                <Button variant="danger" onClick={() => remove.mutate(p.id)}>{t('projects.delete')}</Button>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </Dialog>
  )
}
