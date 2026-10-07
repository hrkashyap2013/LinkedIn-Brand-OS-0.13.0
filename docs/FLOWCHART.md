# 360 flow chart: agents and workflows

These diagrams render automatically on GitHub. Purple = agent, amber = your decision, grey = system step.

## 1. Weekly cycle (28 agents, four decisions)

```mermaid
flowchart TD
  SCH["Trigger<br/>scheduled task or manual"] --> GOV1["Governance"]
  GOV1 --> BI["Brand Intelligence"]
  BI --> CI["Content Intelligence"]
  CI <--> AR["Anti-Repetition"]
  CI --> IG["Idea Generation<br/>exactly 3 ideas"]
  IG --> N1["Notify<br/>desktop and phone"]
  N1 --> D1{{"DECISION 1<br/>you pick one idea"}}
  D1 --> IS["Idea Selection"]
  IS --> RS["Research"]
  RS --> WR["Writing"]
  WR --> HU["Humanization"]
  HU --> VS["Visual Strategy"]
  VS --> VL["Visual Learning<br/>3 previews"]
  VL --> D2{{"DECISION 2<br/>you pick 1 of 3"}}
  D2 --> VP["Visual Production<br/>SVG, PDF, PNG"]
  VP --> VQ["Visual QA<br/>quality gate"]
  VQ -- "below gate" --> VP
  VQ -- "pass" --> GOV2["Governance<br/>final check"]
  GOV2 --> D3{{"DECISION 3<br/>you approve content and visual"}}
  D3 --> PU["Publishing<br/>assembles package"]
  PU --> D4{{"DECISION 4<br/>you approve the package"}}
  D4 --> PO["Posting<br/>ready-to-paste package (you post it)"]
  PO --> LV["You run /live<br/>choose reminder windows"]
  LV --> ME["Measurement"]
  ME --> EX["Experiment"]
  EX --> LE["Learning"]
  LE --> SL["Strategy Learning"]
  SL --> LI["Listening<br/>verifies memory"]
  LI --> SCH
  classDef agent fill:#EEEDFE,stroke:#534AB7,color:#26215C
  classDef human fill:#FAEEDA,stroke:#854F0B,color:#412402
  classDef sys fill:#F1EFE8,stroke:#5F5E5A,color:#2C2C2A
  class GOV1,BI,CI,AR,IG,IS,RS,WR,HU,VS,VL,VP,VQ,GOV2,PU,PO,ME,EX,LE,SL,LI agent
  class D1,D2,D3,D4,LV human
  class SCH,N1 sys
```

## 2. System architecture (360 view)

```mermaid
flowchart TB
  AUTH["Authority<br/>brand profile, schedule, locked decisions"]
  subgraph TRIG["Ways to start"]
    T1["Scheduler (automatic)"]
    T2["Commands and names"]
    T3["@ menu, browser and terminal apps"]
    T4["Auto mode"]
  end
  ORCH["Orchestrator (main agent)"]
  subgraph TEAMS["27 specialist agents, Governance checks every handoff"]
    P["Prepare<br/>Governance, Brand Intelligence,<br/>Content Intelligence, Anti-Repetition,<br/>Idea Generation"]
    C["Create<br/>Idea Selection, Research,<br/>Writing, Humanization"]
    V["Visual<br/>Visual Strategy, Visual Learning,<br/>Visual Production, Visual QA"]
    S["Ship<br/>Publishing, Posting"]
    L["Learn<br/>Measurement, Experiment,<br/>Learning, Strategy Learning"]
    H["Hubs<br/>Listening, Brand"]
  end
  GUARD["Write guard<br/>permission, backup, lock, verify, undo"]
  MEM["Memory: 10 registers + brand profile"]
  HUM["Your decisions<br/>idea, visual, content, package"]
  AUTH --> TRIG
  TRIG --> ORCH
  ORCH --> TEAMS
  TEAMS --> GUARD
  GUARD <--> MEM
  TEAMS --> HUM
  classDef agent fill:#EEEDFE,stroke:#534AB7,color:#26215C
  classDef human fill:#FAEEDA,stroke:#854F0B,color:#412402
  classDef sys fill:#F1EFE8,stroke:#5F5E5A,color:#2C2C2A
  class P,C,V,S,L,H,ORCH agent
  class HUM human
  class AUTH,MEM,GUARD,T1,T2,T3,T4 sys
```

## 3. Memory: who writes what

```mermaid
flowchart LR
  AG["Agents return<br/>REGISTER ENTRY blocks"] --> LI["Listening checks<br/>conflicts, duplicates, sensitive data"]
  LI --> WG["Write guard<br/>permission, backup, lock, verify"]
  WG --> R1["Content Memory"]
  WG --> R2["Visual Memory"]
  WG --> R3["Experiment Register"]
  WG --> R4["Change Register"]
  WG --> R5["Learning Register"]
  WG --> R6["Ideas and Examples"]
  WG --> R7["Experience Bank"]
  WG --> R8["Post Tracker"]
  WG --> R9["Evidence Library"]
  WG --> R10["Approval Log"]
  BR["Brand proposes<br/>profile changes"] --> OW{{"You approve"}}
  OW --> LI2["Listening saves<br/>via profile-set"]
  classDef agent fill:#EEEDFE,stroke:#534AB7,color:#26215C
  classDef human fill:#FAEEDA,stroke:#854F0B,color:#412402
  classDef sys fill:#F1EFE8,stroke:#5F5E5A,color:#2C2C2A
  class AG,LI,BR,LI2 agent
  class OW human
  class WG,R1,R2,R3,R4,R5,R6,R7,R8,R9,R10 sys
```

## 4. Automation: scheduler, manual start, metrics

```mermaid
flowchart LR
  CFG["docs/schedule.json<br/>slots, offset, lead time, pause"] --> REG["register-schedule<br/>cron or Task Scheduler"]
  REG --> TASK["OS scheduled task"]
  TASK --> RUN["run-scheduled<br/>claude -p or codex exec"]
  MAN["Manual start<br/>run-scheduled or /scheduled"] --> RUN
  RUN --> OUT["runs/DATE-SLOT.md<br/>3 ideas + freshness note"]
  OUT --> NOT["Notification"]
  NOT --> YOU["You reply with the idea number"]
  YOU --> CONT["Orchestrator continues<br/>from the prepared run"]
  CSV["Analytics CSV, table or screenshot"] --> MET["metrics.py or guided entry"]
  MET --> DASH["reports/dashboard-DATE.md"]
  DASH --> ME["Measurement"]
  classDef human fill:#FAEEDA,stroke:#854F0B,color:#412402
  classDef sys fill:#F1EFE8,stroke:#5F5E5A,color:#2C2C2A
  class YOU human
  class CFG,REG,TASK,RUN,MAN,OUT,NOT,CONT,CSV,MET,DASH,ME sys
```

## 5. What happens on each agent state

```mermaid
flowchart TD
  X["Any agent finishes<br/>returns one standard state"] --> PR["PROCEED<br/>next agent"]
  X --> RV["REVISE<br/>back to the maker, max 2 loops"]
  X --> HD["HOLD<br/>wait for your decision"]
  X --> ST["STOP<br/>escalate to you"]
  X --> IE["INSUFFICIENT EVIDENCE<br/>you supply real proof"]
  X --> NS["NO MEANINGFUL SIGNAL<br/>record it, keep baseline"]
  F["Anti-Repetition<br/>CLEAR, REWORK, BLOCK"] -- "REWORK or BLOCK" --> IG["Idea Generation<br/>new ideas"]
  classDef agent fill:#EEEDFE,stroke:#534AB7,color:#26215C
  classDef human fill:#FAEEDA,stroke:#854F0B,color:#412402
  classDef sys fill:#F1EFE8,stroke:#5F5E5A,color:#2C2C2A
  class PR,RV,F,IG agent
  class HD,ST,IE human
  class X,NS sys
```

## 6. Command to agent map

| Command | Agent(s) | Output |
|---------|----------|--------|
| `/next` | Governance, Brand Intelligence, Content Intelligence, Anti-Repetition, Idea Generation | Exactly 3 ideas |
| `/lock` | Idea Selection | Selected Idea Brief |
| `/research` | Research | Evidence Pack |
| `/write` (`/draft`) | Writing | Post Draft |
| `/humanize` | Humanization | Humanized Draft |
| `/visual` | Visual Strategy, Visual Learning, then Visual Production and Visual QA after your pick | 3 previews, then the rendered visual |
| `/visualqa` | Visual QA | QA result and score |
| `/audit` | Governance | Governance Status |
| `/package` | Publishing | Publishing Package |
| `/publish` | Posting | Posting Instruction and Result |
| `/review` | Measurement, Experiment | Measurement Record, Experiment Status |
| `/learn` | Learning, Listening, write guard | Learning Record, memory updated |
| `/weekly`, `/monthly` | Strategy Learning (and Brand for the monthly brief) | Strategy Brief |
| `/idea`, `/example` | Listening | Filed in Ideas and Examples |
| `/live` | Posting data into the Post Tracker | Final text, link, reminder windows |
| `/metrics` | Measurement | Guided entry |
| `/comments` | Brand | Risk flags and reply drafts |
| `/undo`, `/export`, `/forget` | Write guard | Restore, zip, delete |
| `/auto`, `/scheduled`, `/orchestrator` | Orchestrator | Pipeline, slot preparation, direct chat |
| `/governance` ... `/brand` | The agent of that name | Its own output |
