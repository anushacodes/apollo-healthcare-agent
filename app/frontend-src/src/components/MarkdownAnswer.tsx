import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

export function MarkdownAnswer({ children }: { children: string }) {
  return (
    <div className="answer-markdown">
      <Markdown
        remarkPlugins={[remarkGfm]}
        skipHtml
        disallowedElements={['img']}
        components={{
          h1: 'h3', h2: 'h3',
          table: ({ children }) => <div className="overflow-x-auto"><table>{children}</table></div>,
          a: ({ href, children }) => <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>,
        }}
      >
        {children}
      </Markdown>
    </div>
  )
}
