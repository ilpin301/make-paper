-- Convert every table from pandoc's longtable output (which errors inside
-- LaTeX \twocolumn) into a tabular wrapped in a float: `table` for narrow
-- tables, `table*` (spans both columns) for wide ones (>= 4 columns).
local WIDE_COLUMNS = 4

function Table(tbl)
  local ncols = #tbl.colspecs
  local caption = pandoc.utils.stringify(tbl.caption.long)
  tbl.caption = pandoc.Caption()

  local latex = pandoc.write(pandoc.Pandoc({ tbl }), "latex")
  latex = latex:gsub("\\begin{longtable}%[[^%]]*%]", "\\begin{tabular}")
  latex = latex:gsub("\\end{longtable}", "\\end{tabular}")

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
