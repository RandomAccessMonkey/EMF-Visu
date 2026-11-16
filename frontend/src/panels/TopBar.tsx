import { Crosshair, FolderOpen, Focus, MousePointer2, Move3d, Rotate3d, Scaling, Zap } from 'lucide-react'
import { useState } from 'react'
import { Button, Segmented } from '@/components/ui/controls'
import { useT } from '@/i18n'
import { useSceneStore } from '@/state/sceneStore'
import { useViewStore } from '@/state/viewStore'
import { ProjectsDialog } from './ProjectsDialog'

export function TopBar() {
  const { t } = useT()
  const v = useViewStore()
  const projectName = useSceneStore((s) => s.projectName)
  const [projectsOpen, setProjectsOpen] = useState(false)
  return (
    <header className="flex flex-wrap items-center gap-x-3 gap-y-1.5 border-b border-border bg-panel px-3 py-1.5">
      <div className="flex items-center gap-2">
        <Zap size={16} className="text-accent drop-shadow-[0_0_6px_rgba(56,189,248,0.8)]" />
        <h1 className="text-sm font-semibold tracking-wide">EMF-Visu</h1>
        {projectName && <span className="max-w-40 truncate text-xs text-muted">· {projectName}</span>}
      </div>
      <Segmented label={t('top.viewMode')} value={v.mode} onChange={(mode) => v.set({ mode })} options={[
        { value: '2d', label: '2D', title: t('top.mode2d') },
        { value: '3d', label: '3D', title: t('top.mode3d') },
      ]} />
      <Segmented label={t('top.tool')} value={v.tool} onChange={(tool) => v.set({ tool })} options={[
        { value: 'select', label: <><MousePointer2 size={12} /> {t('top.select')}</>, title: t('top.selectHint') },
        { value: 'probe', label: <><Crosshair size={12} /> {t('top.probe')}</>, title: t('top.probeHint') },
      ]} />
      {v.mode === '3d' && v.tool === 'select' && (
        <Segmented label={t('top.gizmo')} value={v.transformMode} onChange={(transformMode) => v.set({ transformMode })} options={[
          { value: 'translate', label: <Move3d size={13} />, title: t('top.translate') },
          { value: 'rotate', label: <Rotate3d size={13} />, title: t('top.rotate') },
          { value: 'scale', label: <Scaling size={13} />, title: t('top.scale') },
        ]} />
      )}
      <Button variant="ghost" title={t('top.resetCamera')} onClick={() => v.set({ cameraResetToken: v.cameraResetToken + 1 })}>
        <Focus size={13} /> {t('top.resetCamera')}
      </Button>
      <div className="ml-auto flex items-center gap-2">
        <Button onClick={() => setProjectsOpen(true)}>
          <FolderOpen size={13} /> {t('top.projects')}
        </Button>
        <Segmented label={t('top.level')} value={v.level} onChange={(level) => v.set({ level })} options={[
          { value: 'beginner', label: t('top.beginner'), title: t('top.beginnerHint') },
          { value: 'advanced', label: t('top.advanced'), title: t('top.advancedHint') },
        ]} />
        <Segmented label={t('top.language')} value={v.lang} onChange={(lang) => v.set({ lang })} options={[
          { value: 'en', label: 'EN', title: 'English' },
          { value: 'hu', label: 'HU', title: 'Magyar' },
        ]} />
      </div>
      <ProjectsDialog open={projectsOpen} onOpenChange={setProjectsOpen} />
    </header>
  )
}
