-- make-paper paper_style filter (applied in BOTH layouts):
--  * tables  -> tabular in table/table* floats, cells centered H+V
--    (pandoc's longtable errors inside LaTeX \twocolumn; floats also give
--    uniform centering in single-column)
--  * display math -> numbered equation environments  (1), (2), ...
local WIDE_COLUMNS = 4

function Table(tbl)
  local ncols = #tbl.colspecs
  local caption = pandoc.utils.stringify(tbl.caption.long)
  tbl.caption = pandoc.Caption()
  for i, spec in ipairs(tbl.colspecs) do
    tbl.colspecs[i] = { pandoc.AlignCenter, spec[2] }
  end

  local latex = pandoc.write(pandoc.Pandoc({ tbl }), "latex")
  latex = latex:gsub("\\begin{longtable}%[[^%]]*%]", "\\begin{tabular}")
  latex = latex:gsub("\\end{longtable}", "\\end{tabular}")
  -- width-managed columns: p{} -> m{} (vertical centering)
  latex = latex:gsub("\\arraybackslash}p{", "\\arraybackslash}m{")
  -- vertical lines between columns, none at the outer edges:
  -- simple colspecs come as one 'c' run; width-managed ones as one
  -- '... \real{x.xxxx}}' line per column
  latex = latex:gsub("(\\begin{tabular}{@{})(c+)(@{})", function(head, cols, tail)
    return head .. cols:gsub("c", "c|"):sub(1, -2) .. tail
  end)
  latex = latex:gsub("(\\real{[%d%.]+}})(\n%s*>)", "%1|%2")

  -- longtable emits: header lines, \endhead, footer lines (\bottomrule),
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

  local env = (ncols >= WIDE_COLUMNS) and "table*" or "table"
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
