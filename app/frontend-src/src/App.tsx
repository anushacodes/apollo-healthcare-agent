import { useEffect, useState } from 'react'
import { api } from './api'
import { PatientHeader } from './components/PatientHeader'
import { Sidebar } from './components/Sidebar'
import { AskTab } from './tabs/AskTab'
import { DiagnosticsTab } from './tabs/DiagnosticsTab'
import { DocumentsTab } from './tabs/DocumentsTab'
import { SummaryTab } from './tabs/SummaryTab'
import type { CaseListItem, PatientData } from './types'

type TabId = 'summary' | 'diagnostics' | 'ask' | 'documents'

const TABS: { id: TabId; label: string }[] = [
  { id: 'summary', label: 'Summary' },
  { id: 'diagnostics', label: 'Diagnostics' },
  { id: 'ask', label: 'Ask' },
  { id: 'documents', label: 'Documents' },
]

export default function App() {
  const [cases, setCases] = useState<CaseListItem[]>([])
  const [patient, setPatient] = useState<PatientData | null>(null)
  const [activeTab, setActiveTab] = useState<TabId>('summary')
  const [kgStatus, setKgStatus] = useState('Knowledge base — checking…')

  useEffect(() => {
    api
      .getCases()
      .then(setCases)
      .catch(() => setCases([{ key: 'case_a', label: 'Case A — James Hartwell (SLE / Lupus Nephritis)' }]))

    api
      .getKgStatus()
      .then((s) => setKgStatus(`Knowledge base — ${s.local_conditions} conditions`))
      .catch(() => setKgStatus('Knowledge base unavailable'))

    const params = new URLSearchParams(window.location.search)
    const caseParam = params.get('case') || (params.get('demo') === 'true' ? 'case_a' : null)
    if (caseParam) selectCase(caseParam)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function selectCase(key: string) {
    api
      .getCaseData(key)
      .then((data) => {
        data._caseKey = key
        setPatient(data)
        setActiveTab('summary')
        history.replaceState(null, '', `?case=${key}`)
      })
      .catch((err) => console.error('[app] failed to load case', key, err))
  }

  return (
    <div className="flex h-screen bg-gray-50">
      <Sidebar cases={cases} activeKey={patient?._caseKey || null} onSelect={selectCase} kgStatus={kgStatus} />

      <main className="flex min-w-0 flex-1 flex-col">
        {!patient ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-3 text-center">
            <p className="text-sm text-gray-500">Select a demo patient from the sidebar to get started.</p>
          </div>
        ) : (
          <>
            <PatientHeader patient={patient} />

            <nav className="flex gap-1 border-b border-gray-200 bg-white px-6">
              {TABS.map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`border-b-2 px-3 py-3 text-sm font-medium transition ${
                    activeTab === tab.id
                      ? 'border-indigo-600 text-indigo-700'
                      : 'border-transparent text-gray-500 hover:text-gray-800'
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </nav>

            <div className="min-h-0 flex-1 overflow-y-auto">
              {activeTab === 'summary' && <SummaryTab patient={patient} />}
              {activeTab === 'diagnostics' && <DiagnosticsTab patient={patient} />}
              {activeTab === 'ask' && <AskTab patient={patient} />}
              {activeTab === 'documents' && <DocumentsTab patient={patient} isDemo={Boolean(patient._caseKey)} />}
            </div>
          </>
        )}
      </main>
    </div>
  )
}
