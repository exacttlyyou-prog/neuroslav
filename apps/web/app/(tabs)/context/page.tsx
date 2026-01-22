import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { DocumentUploadForm } from "@/components/forms/DocumentUploadForm"
import { KnowledgeSearch } from "@/components/knowledge/KnowledgeSearch"

export default function ContextPage() {
  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>База знаний</CardTitle>
          <CardDescription>
            Загрузи документы — Нейрослав проиндексирует и найдет нужное по смыслу
          </CardDescription>
        </CardHeader>
        <CardContent>
          <DocumentUploadForm />
        </CardContent>
      </Card>
      
      <Card>
        <CardHeader>
          <CardTitle>Поиск</CardTitle>
        </CardHeader>
        <CardContent>
          <KnowledgeSearch />
        </CardContent>
      </Card>
    </div>
  )
}
