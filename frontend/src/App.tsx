import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { SidebarProvider, SidebarTrigger } from '@/components/ui/sidebar'
import { AppSidebar } from '@/components/AppSidebar'
import PipelineMonitoreo from '@/pages/pipeline/PipelineMonitoreo'
import PipelineConfiguracion from '@/pages/pipeline/PipelineConfiguracion'

export default function App() {
  return (
    <BrowserRouter>
      <SidebarProvider>
        <AppSidebar />
        <main className="flex-1 p-4">
          <SidebarTrigger className="mb-4" />
          <Routes>
            <Route path="/" element={<Navigate to="/pipeline/monitoreo" replace />} />
            <Route path="/pipeline/monitoreo" element={<PipelineMonitoreo />} />
            <Route path="/pipeline/configuracion" element={<PipelineConfiguracion />} />
          </Routes>
        </main>
      </SidebarProvider>
    </BrowserRouter>
  )
}
