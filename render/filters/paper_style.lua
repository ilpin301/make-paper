-- make-paper paper_style filter (applied in BOTH layouts):
--  * tables  -> tabular in table/table* floats, cells centered H+V, full
--    grid borders, light-blue header row (v2.3, after the 01.jpg sample)
--    (pandoc's longtable errors inside LaTeX \twocolumn; floats also give
--    uniform centering in single-column)
--  * tables too wide for a two-column-layout column span the full page
--  * display math -> numbered equation environments  (1), (2), ...
--  * references switch back to one column (full width) in two-column layout
local WIDE_COLUMNS = 4
local CHAR_BUDGET = 45   -- ~ chars fitting one column at \small, incl. padding

local function estimated_width(tbl)
  -- widest cell per column, in characters (bytes overcount umlauts a bit,
  -- which only errs toward spanning — acceptable)
  local widths = {}
  local function scan(rows)
    for _, row in ipairs(rows) do
      for i, cell in ipairs(row.cells) do
        local n = #pandoc.utils.stringify(cell)
        if n > (widths[i] or 0) then widths[i] = n end
      end
    end
  end
  scan(tbl.head.rows)
  for _, body in ipairs(tbl.bodies) do scan(body.body) end
  local total = 0
  for _, w in pairs(widths) do total = total + w + 3 end
  return total
end

function Table(tbl)
  local ncols = #tbl.colspecs
  local wide = ncols >= WIDE_COLUMNS or estimated_width(tbl) > CHAR_BUDGET
  -- the caption goes into a RawBlock, so write it through the latex writer
  -- to escape specials (a raw % would comment out \caption's closing brace)
  local caption = ""
  if pandoc.utils.stringify(tbl.caption.long) ~= "" then
    caption = pandoc.write(pandoc.Pandoc(tbl.caption.long), "latex")
                :gsub("%s+$", "")
  end
  tbl.caption = pandoc.Caption()
  for i, spec in ipairs(tbl.colspecs) do
    tbl.colspecs[i] = { pandoc.AlignCenter, spec[2] }
  end

  local latex = pandoc.write(pandoc.Pandoc({ tbl }), "latex")
  latex = latex:gsub("\\begin{longtable}%[[^%]]*%]", "\\begin{tabular}")
  latex = latex:gsub("\\end{longtable}", "\\end{tabular}")
  -- width-managed columns: p{} -> m{} (vertical centering)
  latex = latex:gsub("\\arraybackslash}p{", "\\arraybackslash}m{")
  -- vertical lines between columns: simple colspecs come as one 'c' run;
  -- width-managed ones as one '... \real{x.xxxx}}' line per column
  latex = latex:gsub("(\\begin{tabular}{@{})(c+)(@{})", function(head, cols, tail)
    return head .. cols:gsub("c", "c|"):sub(1, -2) .. tail
  end)
  latex = latex:gsub("(\\real{[%d%.]+}})(\n%s*>)", "%1|%2")
  -- full outer border: drop the @{} edge suppression for |…| (rule v2.3)
  latex = latex:gsub("(\\begin{tabular}{)@{}", "%1|")
  latex = latex:gsub("@{}}", "|}")
  -- uniform grid: booktabs rules -> \hline so the verticals meet them
  latex = latex:gsub("\\toprule", "\\hline")
  latex = latex:gsub("\\midrule", "\\hline")
  latex = latex:gsub("\\bottomrule", "\\hline")

  -- longtable emits: header lines, \endhead, footer lines (bottom rule),
  -- \endlastfoot, body rows. Drop the markers and move the footer to the end.
  local out, footer, in_footer = {}, {}, false
  for line in (latex .. "\n"):gmatch("(.-)\n") do
    if line == "\\endfirsthead" or line == "\\endfoot" then
      -- drop
    elseif line == "\\endhead" then
      in_footer = true
    elseif line == "\\endlastfoot" then
      in_footer = false
    elseif in_footer then
      table.insert(footer, line)
    elseif line == "\\end{tabular}" then
      for _, f in ipairs(footer) do table.insert(out, f) end
      table.insert(out, line)
    else
      table.insert(out, line)
    end
  end

  -- light-blue header row: first row after the top rule (rule v2.3)
  for idx, line in ipairs(out) do
    if line:match("^\\hline") then
      table.insert(out, idx + 1, "\\rowcolor{tableheadbg}")
      break
    end
  end

  local env = wide and "table*" or "table"
  local pieces = { "\\begin{" .. env .. "}[t]", "\\centering", "\\small",
                   table.concat(out, "\n") }
  if caption ~= "" then
    table.insert(pieces, "\\caption{" .. caption .. "}")
  end
  table.insert(pieces, "\\end{" .. env .. "}")
  return pandoc.RawBlock("latex", table.concat(pieces, "\n"))
end

function Math(m)
  if m.mathtype == "DisplayMath" then
    return pandoc.RawInline("latex",
      "\\begin{equation}" .. m.text .. "\\end{equation}")
  end
end

-- References full width: like the abstract, the Literaturverzeichnis runs
-- in one column (rule v2.3-1). \if@twocolumn makes this a no-op in the
-- one-column layout without any metadata plumbing.
function Pandoc(doc)
  for i, blk in ipairs(doc.blocks) do
    if blk.t == "Header" and blk.classes:includes("unnumbered")
        and pandoc.utils.stringify(blk):lower() == "literaturverzeichnis" then
      doc.blocks:insert(i, pandoc.RawBlock("latex",
        "\\makeatletter\\if@twocolumn\\onecolumn\\fi\\makeatother"))
      return doc
    end
  end
end
