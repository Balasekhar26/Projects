from pathlib import Path

app_path = Path("/Users/alwaysdesigns/Documents/Codex/2026-06-23/balasekhar26-ult-translator-https-github-com/work/ult-translator/kattappa/dashboard/src/App.tsx")
content = app_path.read_text(encoding="utf-8")

obs_start_str = "          {cognitiveTab === 'observatory' && ("
mral_start_str = "          {cognitiveTab === 'mral' && ("

idx_obs = content.find(obs_start_str)
idx_mral = content.find(mral_start_str)

if idx_obs == -1 or idx_mral == -1:
    print(f"Error: Observatory block or MRAL block start not found. idx_obs={idx_obs}, idx_mral={idx_mral}")
    exit(1)

# Verify mral block end
# The end of the mral block inside the cognitive mode return statement is followed by:
#         </div>
#       </div>
#     );
#   }
mral_end_str = "            </div>\n          )}\n        </div>\n      </div>\n    );\n  }"
# Let's search for this block starting from idx_mral
idx_mral_end = content.find(mral_end_str, idx_mral)
if idx_mral_end == -1:
    # Try different spacing/newlines
    mral_end_str = "            </div>\n          )}\n        </div>\n      </div>\n    );\n  }"
    # Let's do a more robust find
    # The end of activeDashboardMode === 'cognitive' return block is:
    #       </div>
    #     );
    #   }
    # which is followed by:
    #   return (
    idx_cog_end = content.find("      return (\n    <div className=\"dashboard\">")
    if idx_cog_end == -1:
        # try without space or different quotes
        idx_cog_end = content.find("  return (")
    
    # The mral block ends right before the closing divs of the cognitive dashboard view:
    #         </div>
    #       </div>
    #     );
    #   }
    # So we search backwards from idx_cog_end for ")}"
    idx_mral_end_close = content.rfind(")}", idx_mral, idx_cog_end)
    if idx_mral_end_close == -1:
        print("Error: Could not determine end of MRAL block.")
        exit(1)
    idx_mral_end = idx_mral_end_close + 2
else:
    # mral_end_str ends with the closing of mral block which is idx_mral_end + len("            </div>\n          )}")
    idx_mral_end = content.find(")}", idx_mral_end) + 2

print(f"Observatory block: [{idx_obs} : {idx_mral}]")
print(f"MRAL block: [{idx_mral} : {idx_mral_end}]")

new_obs_block = """          {cognitiveTab === 'observatory' && (
            <MemoryPanel cognitiveSnapshot={cognitiveSnapshot} />
          )}

"""

new_mral_block = """          {cognitiveTab === 'mral' && (
            <TasksPanel goals={goals} onRefreshGoals={fetchData} API_BASE={API_BASE} />
          )}

          {cognitiveTab === 'ledger' && (
            <LedgerPanel
              ledgerEvents={ledgerEvents}
              selectedLedgerEventId={selectedLedgerEventId}
              onSelectEvent={setSelectedLedgerEventId}
              ancestors={ledgerEventAncestors}
              descendants={ledgerEventDescendants}
              API_BASE={API_BASE}
            />
          )}"""

# Reconstruct file content
new_content = (
    content[:idx_obs]
    + new_obs_block
    + new_mral_block
    + content[idx_mral_end:]
)

app_path.write_text(new_content, encoding="utf-8")
print("Successfully cleaned App.tsx!")
