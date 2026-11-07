import { useEffect, useRef, useState } from 'react'
import { api } from './api'
import { PatientHeader } from './components/PatientHeader'
import { Sidebar } from './components/Sidebar'
import { BrandMark, Icon, type IconName } from './components/Icon'
import { AskTab } from './tabs/AskTab'
import { DiagnosticsTab } from './tabs/DiagnosticsTab'
import { DocumentsTab } from './tabs/DocumentsTab'
import { SummaryTab } from './tabs/SummaryTab'
import type { CaseListItem, PatientData } from './types'

type TabId = 'summary' | 'diagnostics' | 'ask' | 'documents'

const TABS: { id: TabId; label: string; icon: IconName }[] = [
  { id: 'summary', label: 'Overview', icon: 'overview' },
  { id: 'diagnostics', label: 'Analysis', icon: 'analysis' },
  { id: 'ask', label: 'Ask', icon: 'ask' },
  { id: 'documents', label: 'Documents', icon: 'document' },
]

export default function App() {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [cases, setCases] = useState<CaseListItem[]>([])
  const [patient, setPatient] = useState<PatientData | null>(null)
  const [activeTab, setActiveTab] = useState<TabId>('summary')
  const [loadError, setLoadError] = useState('')
  const selectionRef = useRef(0)

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const caseParam = params.get('case') || (params.get('demo') === 'true' ? 'case_a' : null)
    api
      .getCases()
      .then((items) => {
        setCases(items)
        if (!caseParam && items.length) selectCase(items[0].key)
      })
      .catch(() => setLoadError('Could not load patients. Please reload to try again.'))

    if (caseParam) selectCase(caseParam)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function selectCase(key: string) {
    const selection = ++selectionRef.current
    setLoadError('')
    setSidebarOpen(false)
    api
      .getCaseData(key)
      .then((data) => {
        if (selection !== selectionRef.current) return
        data._caseKey = key
        setPatient(data)
        setActiveTab('summary')
        history.replaceState(null, '', `?case=${key}`)
      })
      .catch(() => {
        if (selection === selectionRef.current) setLoadError('Could not load this patient. Choose a patient to try again.')
      })
  }

  async function refreshRecord() {
    const key = patient?._caseKey
    const selection = selectionRef.current
    if (!key) return
    const updated = await api.getCaseData(key)
    if (selection === selectionRef.current) setPatient({ ...updated, _caseKey: key })
  }

  return (
    <div className="flex h-dvh flex-col bg-paper font-sans text-ink lg:flex-row">
      <div className="mobile-workspace-bar flex shrink-0 items-center justify-between px-4 py-3 lg:hidden">
        <span className="mobile-brand"><BrandMark />Apollo</span>
        <button className="secondary-button" aria-expanded={sidebarOpen} aria-controls="patient-selector" onClick={() => setSidebarOpen(!sidebarOpen)}>
          {sidebarOpen ? 'Hide patients' : 'Choose patient'}
        </button>
      </div>
      <div id="patient-selector" className={`${sidebarOpen ? 'block' : 'hidden'} shrink-0 lg:block lg:h-full`}>
        <Sidebar cases={cases} activeKey={patient?._caseKey || null} onSelect={selectCase} />
      </div>

      <main className="flex min-h-0 min-w-0 flex-1 flex-col">
        {loadError && <p role="alert" className="border-b border-critical/30 p-4 text-base text-critical">{loadError}</p>}
        {!patient ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-3 text-center">
            <p className="text-base text-muted">Choose a patient to view their records.</p>
          </div>
        ) : (
          <>
            <PatientHeader patient={patient} />

            <nav aria-label="Patient sections" className="workspace-tabs">
              {TABS.map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  aria-current={activeTab === tab.id ? 'page' : undefined}
                  className="workspace-tab"
                >
                  <Icon name={tab.icon} />
                  {tab.label}
                </button>
              ))}
            </nav>

            <div key={`${patient.patient_id}:${activeTab}`} className="tab-enter min-h-0 flex-1 overflow-y-auto">
              {activeTab === 'summary' && <SummaryTab patient={patient} />}
              {activeTab === 'diagnostics' && <DiagnosticsTab patient={patient} />}
              {activeTab === 'ask' && <AskTab patient={patient} />}
              {activeTab === 'documents' && <DocumentsTab patient={patient} onRecordChange={refreshRecord} />}
            </div>
          </>
        )}
      </main>
    </div>
  )
}
