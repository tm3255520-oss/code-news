Source: https://raw.githubusercontent.com/wienkers/obsidian-research-mcp/main/README.md
Fetched: 2026-08-01T10:38:33

# Obsidian Research MCP

A **Model Context Protocol (MCP)** server enabling Claude to read, write, search, and analyse your Obsidian vault with advanced research capabilities.

## 🌟 Core Capabilities

**8 consolidated tools** providing comprehensive vault operations:

### 🧠 Semantic Search
```
Find notes conceptually related to "machine learning interpretability" 
with high precision matching
```
- **Smart Connections integration** for concept-based search
- **Advanced filtering** by folders, tags, linked files, frontmatter properties
- **Link expansion** with configurable traversal depth
- **Similarity thresholds** for precision control

### 🔍 Pattern Search  
```
Extract all TODO items and incomplete tasks across my vault, 
showing where they appear and usage statistics
```
- **Multiple regex patterns** with frequency analysis
- **Context windows** around matches
- **Scoped searching** with include/exclude filters
- **Usage statistics** and insights

### 📄 Note Operations
```
Get my "AI Ethics" note with creation date, file size, 
and word count in structured JSON format
```
- **Batch retrieval** of multiple notes efficiently
- **File statistics** with formatted timestamps and token counts
- **JSON/Markdown formats** with comprehensive metadata
- **Auto-resolution** from basenames to full paths

### ✏️ Precision Writing
```
Add new findings section after the "Results" heading 
in my research paper without disrupting the structure
```
- **Surgical positioning** relative to headings, frontmatter, or line ranges
- **Whole-file operations** (overwrite, append, prepend)
- **Automatic frontmatter preservation**
- **Active note targeting** for current Obsidian file

### 🗂️ Vault Exploration
```
Show me all recent markdown files in my Projects folder, 
excluding drafts and temporary files
```
- **Advanced filtering** by extension, date range, name patterns
- **Content statistics** for text files (word count, line count)
- **Recursive exploration** with configurable depth
- **Overview/detailed modes** for different use cases

### 🔗 Relationship Analysis
```
Map all the connections between my project notes - 
which ones reference each other and how they're linked
```
- **Comprehensive relationship types**: backlinks, forward links, tags, mentions, embeds
- **Batch analysis** across multiple files
- **Contextual evidence** with line numbers and surrounding text
- **Strength scoring** and filtering thresholds

### 📊 Content Analysis
```
Break down the structure of my research paper and 
extract just the "Results" section with its subsections
```
- **Document structure extraction** (headings, lists, code blocks, tasks, tables)
- **Advanced section targeting** by heading text, line ranges, or regex patterns
- **Hierarchical analysis** with parent/child relationships
- **Rich metadata** including word counts and content classification

### 🔧 File Management
```
Rename my project file and automatically update 
all the links pointing to it throughout my vault
```
- **Link-aware operations** automatically updating all references
- **Batch text operations** with regex and smart case preservation
- **Safety features**: dry-run preview, backups, comprehensive error handling
- **Find-replace** across vault with flexible scoping

## 🚀 Quick Setup

### Prerequisites
- **Node.js 18+**
- **Obsidian** with **Local REST API** and **Smart Connections** plugins

### Installation

1. **Install Dependencies**
   ```bash
   # In Obsidian: Install "Local REST API" and "Smart Connections" plugins
   # Enable Local REST API (starts on port 27124, note the API key)
   ```

2. **Build MCP Server**
   ```bash
   git clone <repository-url>
   cd obsidian-research-mcp
   npm install && npm run build
   ```

3. **Install Obsidian Plugin**
   ```bash
   cp -r packages/obsidian-plugin/ /path/to/vault/.obsidian/plugins/obsidian-research-mcp/
   # Enable "Research MCP Bridge" in Obsidian settings
   ```

4. **Configure Claude Desktop**
   
   Use the plugin's **"Configure Claude Desktop"** command or manually add to `claude_desktop_config.json`:
   
   ```json
   {
     "mcpServers": {
       "obsidian-research-mcp": {
         "command": "node",
         "args": ["/path/to/obsidian-research-mcp/packages/mcp-server/dist/index.js"],
         "env": {
           "OBSIDIAN_API_KEY": "your_api_key_from_local_rest_api",
           "OBSIDIAN_API_URL": "https://127.0.0.1:27124",
           "OBSIDIAN_VAULT_PATH": "/path/to/your/vault"
         }
       }
     }
   }
   ```

5. **Test Connection**
   ```
   Restart Claude Desktop and ask: "Can you read my Obsidian notes?"
   ```

## 🏗️ Architecture

```
Claude Desktop ←→ MCP Server ←→ Local REST API ←→ Obsidian Vault
                      ↓
               Smart Connections
```

- **Obsidian Plugin**: Bridges Local REST API with Smart Connections
- **MCP Server**: Standalone process with 8 consolidated tools  
- **Local Communication**: HTTPS on localhost (port 27124)
- **Link Integrity**: Automatic maintenance across all operations

## 🔍 Example Workflows

**Research Analysis**
```
1. Find notes about "neural networks" using semantic search
2. Analyse relationships between the top 3 results  
3. Extract all citations and TODOs from these notes
4. Create a summary note with findings
```

**Content Organisation**
```
1. Explore my Research folder for files modified this month
2. Find all incomplete tasks using pattern search
3. Update the project status in my dashboard note
4. Rename and reorganise files whilst maintaining links
```

**Knowledge Discovery**
```
1. Search for concepts related to my current research using Smart Connections
2. Map relationships between key papers and notes
3. Identify knowledge gaps and missing connections
4. Generate new research questions and next steps
```

## 🛡️ Security & Performance

- **Local-only communication** - no external network access required
- **SSL/HTTPS** with certificate bypass for self-signed certificates  
- **Rate limiting** and comprehensive error handling
- **Cached indices** for efficient relationship analysis
- **Batch operations** for optimal performance

---

*Transform your Obsidian vault into an intelligent research assistant with Claude.*

