# `filelist` Graph Dataflow Diagram

[Back to the `filelist` graph](filelist.md) · [graphs index](index.md)

The full dataflow of the `filelist` graph, rendered inline by GitHub. Node labels note the module and pairing contract in parentheses; edge labels show the payloads carried (`port:Type`). Colour key: solid blue = main pipeline, amber dashed = config/base_dir, purple = flag-gated bypass, green = CLI inputs. Gate nodes are purple-filled.

```mermaid
flowchart TD
  workdir["work-dir<br/>(default)"] h1@-->|"dir:Path"| config_path["config-path<br/>(dirjoin, unit)"]
  config_path h2@-->|"model_path:Path"| load["load-model<br/>(default)"]
  config_path h3@-->|"path:Path"| modeldir["model-dir<br/>(dirname, unit)"]
  load m1@-->|"model:ModelConfig"| extract["extract<br/>(filelist-extract, default)"]
  modeldir c1@-->|"base_dir:Path"| extract

  extract m3@-->|"entries:list[entry]"| normalise["normalise<br/>(filelist-normalise, default)"]
  outdir["output-dir<br/>(dirname, unit)"] c3@-->|"base_dir:Path"| normalise

  normalise t1@-->|"entries"| gate_flatten["gate-flatten<br/>(flag-gate, default)"]
  gate_flatten t2@-->|"on"| flatten["flatten<br/>(filelist-flatten, default)"]
  flatten t3@-->|"entries"| gate_strip["gate-strip<br/>(flag-gate, default)"]
  gate_flatten b1@-. "off" .-> gate_strip
  gate_strip t4@-->|"on"| strip["strip<br/>(filelist-strip, default)"]
  strip t5@-->|"entries"| gate_dedup["gate-dedup<br/>(flag-gate, default)"]
  gate_strip b2@-. "off" .-> gate_dedup
  gate_dedup t6@-->|"on"| dedup["dedup<br/>(filelist-dedup, default)"]
  dedup t7@-->|"entries"| write["write<br/>(write-filelist, default)"]
  gate_dedup b3@-. "off" .-> write
  write m4@-->|"filelist:Path"| log_filelist["log-filelist<br/>(logger, default)"]

  c_model_name(["model_name"]) g1@-->|"model_name:str"| load
  c_output_path(["output_path"]) g2@-->|"path:Path"| outdir
  c_output_path g3@-->|"path:Path"| write
  c_model_config(["model_config"]) g4@-->|"name:str"| config_path
  c_unroll(["unroll"]) g5@-->|"unroll:bool"| extract
  c_flatten(["flatten"]) g6@-->|"flag:bool"| gate_flatten
  c_strip(["strip_options"]) g7@-->|"flag:bool"| gate_strip
  c_deduplicate(["deduplicate"]) g8@-->|"flag:bool"| gate_dedup

  classDef gate fill:#f3e8ff,stroke:#8250df,stroke-width:2px;
  classDef sink fill:#eef5f5,stroke:#3a7d7d,stroke-width:2px;
  classDef cli fill:#eef7ee,stroke:#2da44e;
  class gate_flatten,gate_strip,gate_dedup gate;
  class log_filelist sink;
  class c_model_name,c_output_path,c_model_config,c_unroll,c_flatten,c_strip,c_deduplicate cli;

  classDef mainEdge stroke:#1f6feb,stroke-width:2px;
  classDef optEdge stroke:#8250df,stroke-width:1.5px,stroke-dasharray:4 3;
  classDef bypassEdge stroke:#6e7781,stroke-width:1.5px,stroke-dasharray:2 4;
  classDef cfgEdge stroke:#bf8700,stroke-width:1.5px;
  classDef cliEdge stroke:#1a7f37,stroke-width:1.5px;
  class h2,m1,m3,t1,t7,m4 mainEdge;
  class t2,t3,t4,t5,t6 optEdge;
  class b1,b2,b3 bypassEdge;
  class h1,h3,c1,c3 cfgEdge;
  class g1,g2,g3,g4,g5,g6,g7,g8 cliEdge;
```
