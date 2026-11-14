# K-Dense static review

Repository: https://github.com/K-Dense-AI/scientific-agent-skills.git

Commit: `2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5`; tree: `390fe361644ba6ef88019af55a45a28ace2014ba`; license: MIT.

177 skills scanned as text; 147 PASS, 30 FAIL; 26 included, 151 excluded.

Scope: the supplied candidate names match upstream exactly; no name mappings needed.

PASS means no configured fail rule matched. This is a conservative lexical review, not proof of safety or a sandbox. Documentation examples and references count as instructions. No pack code was imported or executed. Ordinary dependency install instructions, dynamic operations and service keys are disclosed, not automatically rejected. Clipboard and home/cache access are disclosed; sensitive access is rejected. Only the listed subset may be installed, per lane; service calls still require normal task authorization.

Line numbers are one-based; line 0 denotes a whole-file/continued-command finding. Empty categories have no lexical match. ENV includes shell expansion and documented API-key names, so it can include examples rather than an actual runtime read. Hosts include both URL authorities and bare host references.

## Candidates

| Skill | Result | Included | Reasons | Hosts | Environment variables |
|---|---|---|---|---|---|
| adaptyv | PASS | yes | none | arxiv.org, devs.adaptyvbio.com, docs.adaptyvbio.com, doi.org, export.arxiv.org, foundry.adaptyvbio.com, github.com | ADAPTYV_API_KEY, ADAPTYV_EXPERIMENT_ID, ADAPTYV_TARGET_ID |
| alphagenome | PASS | yes | none | alphagenome.google, arxiv.org, deepmind.google, deepmind.google.com, docs.cloud.google.com, doi.org, export.arxiv.org, gdmscience.googleapis.com:443, github.com, pypi.org, storage.googleapis.com, www.alphagenomedocs.com | ALPHAGENOME_API_KEY, ALPHA_GENOME_API_KEY |
| anndata | PASS | yes | none | anndata.io, anndata.readthedocs.io, arxiv.org, bucket-name, doi.org, export.arxiv.org, github.com, scanpy.readthedocs.io, scverse.org | none |
| biopython | PASS | yes | none | arxiv.org, biopython.org, blast.ncbi.nlm.nih.gov, doi.org, eutils.ncbi.nlm.nih.gov, example.com, export.arxiv.org, github.com, ncbiinsights.ncbi.nlm.nih.gov, pypi.org, www.drive5.com, www.ncbi.nlm.nih.gov | NCBI_API_KEY |
| cellxgene-census | PASS | yes | none | arxiv.org, cellxgene-census-public-us-west-2, census.cellxgene.cziscience.com, chanzuckerberg.github.io, contrib.cellxgene.cziscience.com, doi.org, export.arxiv.org, github.com, pypi.org, scanpy.readthedocs.io, single-cell-data.github.io | none |
| database-lookup | PASS | yes | none | 1.1.1.1, 2.7.11.1, 252Fpurl.obolibrary.org, ClinicalTrials.gov, Clue.io, MyVariant.info, USPTO.gov, alphafold.ebi.ac.uk, api.bls.gov, api.census.gov, api.clinpgx.org, api.clue.io, api.datacommons.org, api.developers.addgene.org, api.drugbank.com, api.fda.gov, api.fiscaldata.treasury.gov, api.gdc.cancer.gov, api.geneontology.org, api.genome.ucsc.edu, api.materialsproject.org, api.monarchinitiative.org, api.nasa.gov, api.ncbi.nlm.nih.gov, api.omim.org, api.openweathermap.org, api.patentsview.org, api.pharmgkb.org, api.platform.opentargets.org, api.stlouisfed.org, api.uspto.gov, api.waterdata.usgs.gov, api.worldbank.org, apikeys.datacommons.org, apps.bea.gov, aqs.epa.gov, arxiv.org, bindingdb.org, cancer.sanger.ac.uk, clinicaltrials.gov, clue.io, dailymed.nlm.nih.gov, data-api.ecb.europa.eu, data.bls.gov, data.ecb.europa.eu, data.epa.gov, data.rcsb.org, data.sdss.org, data.sec.gov, data.uspto.gov, developers.addgene.org, disgenet.org, docs.cbioportal.org, docs.datacommons.org, docs.developers.addgene.org, docs.drugbank.com, docs.materialsproject.org, docs.myvariant.info, doi.org, download.bls.gov, downloads.thebiogrid.org, earthquake.usgs.gov, ec.europa.eu, efts.sec.gov, email.com, europepmc.org, eutils.ncbi.nlm.nih.gov, example.com, exoplanetarchive.ipac.caltech.edu, export.arxiv.org, facts.us, files.rcsb.org, fiscaldata.treasury.gov, fred.stlouisfed.org, ftp.ebi.ac.uk, ftp.ncbi.nlm.nih.gov, genie.cbioportal.org, genome-mysql.soe.ucsc.edu, ghoapi.azureedge.net, github.com, gnomad.broadinstitute.org, golr.geneontology.org, grch37.rest.ensembl.org, gtexportal.org, home.openweathermap.org, home.treasury.gov, jaspar.elixir.no, materialsproject.org, mycompany.com, myvariant.info, ncbi.nlm.nih.gov, omim.org, ontology.jax.org, open.fda.gov, openweathermap.org, patentsview.org, ped.uspto.gov, physics.nist.gov, platform-docs.opentargets.org, platform.opentargets.org, pubchem.ncbi.nlm.nih.gov, purl.obolibrary.org, reactome.org, regulomedb.org, rest.ensembl.org, rest.kegg.jp, rest.uniprot.org, rummageo.com, schlotterer.notion.site, science.nasa.gov, search.patentsview.org, search.rcsb.org, service.azul.data.humancellatlas.org, simbad.cds.unistra.fr, skyserver.sdss.org, string-db.org, support.disgenet.com, tsdr.uspto.gov, tsdrapi.uspto.gov, waterservices.usgs.gov, webbook.nist.gov, webservice.thebiogrid.org, wiki.thebiogrid.org, www.alphavantage.co, www.bindingdb.org, www.brenda-enzymes.org, www.cbioportal.org, www.census.gov, www.crystallography.net, www.disgenet.com, www.ebi.ac.uk, www.encodeproject.org, www.epa.gov, www.kegg.jp, www.metabolomicsworkbench.org, www.mousemine.org, www.ncbi.nlm.nih.gov, www.ncdc.noaa.gov, www.ncei.noaa.gov, www.proteinatlas.org, www.sec.gov, www.uspto.gov, www.who.int, zinc.docking.org | ADDGENE_API_KEY, ALPHAVANTAGE_API_KEY, BEA_API_KEY, BIOGRID_API_KEY, BLS_API_KEY, CENSUS_API_KEY, CLUE_API_KEY, DATACOMMONS_API_KEY, DISGENET_API_KEY, DRUGBANK_API_KEY, FRED_API_KEY, MP_API_KEY, NASA_API_KEY, NCBI_API_KEY, NOAA_API_KEY, OMIM_API_KEY, OPENFDA_API_KEY, OPENWEATHERMAP_API_KEY, USPTO_ODP_API_KEY, YOUR_API_KEY |
| datamol | PASS | yes | none | arxiv.org, bucket, datamol.io, docs.datamol.io, doi.org, export.arxiv.org, github.com, pypi.org, www.rdkit.org | none |
| deepchem | PASS | yes | none | arxiv.org, deepchem.readthedocs.io, doi.org, export.arxiv.org, github.com, huggingface.co, pypi.org, www.dgl.ai | none |
| depmap | PASS | yes | none | depmap.org, doi.org, forum.depmap.org, github.com, ndownloader.figshare.com | none |
| diffdock | PASS | yes | none | arxiv.org, docs.openmm.org, doi.org, export.arxiv.org, github.com, huggingface.co, localhost:7860, posebusters.readthedocs.io | none |
| esm | PASS | yes | none | arxiv.org, biohub.ai, biohub.org, doi.org, export.arxiv.org, github.com, huggingface.co, pypi.org, scikit-learn.org | ESM_API_KEY |
| gget | FAIL | no | LLM-provider key reference/read instruction | api.platform.opentargets.org, arxiv.org, bgee.org, blast.ncbi.nlm.nih.gov, cancer.sanger.ac.uk, data.rcsb.org, doi.org, eightcubedb.onrender.com, elm.eu.org, export.arxiv.org, files.rcsb.org, ftp.ensembl.org, ftp.ensemblgenomes.org, g2p.broadinstitute.org, genome.ucsc.edu, gget.info, github.com, maayanlab.cloud, mysql-eg-publicsql.ebi.ac.uk, rest.ensembl.org, scverse.org, www.cbioportal.org | COSMIC_EMAIL, COSMIC_PASSWORD, OPENAI_API_KEY |
| latchbio-integration | PASS | yes | none | , 12345.account, 67890.node, arxiv.org, console.latch.bio, doi.org, example.org, export.arxiv.org, github.com, mcp.latch.bio, pypi.org, shared, wiki.latch.bio | PATH |
| medchem | PASS | yes | none | arxiv.org, doi.org, dx.doi.org, export.arxiv.org, github.com, medchem-docs.datamol.io, pubmed.ncbi.nlm.nih.gov, pypi.org | none |
| molfeat | PASS | yes | none | arxiv.org, doi.org, export.arxiv.org, fs.molfeat.datamol.io, github.com, huggingface.co, pypi.org | none |
| opentrons-integration | PASS | yes | none | arxiv.org, docs.opentrons.com, doi.org, export.arxiv.org, github.com, labware.opentrons.com, opentrons.com, pypi.org | none |
| pathway-enrichment | PASS | yes | none | arxiv.org, biit.cs.ut.ee, data.broadinstitute.org, decoupler.scverse.org, docs.gsea-msigdb.org, docs.mygene.info, doi.org, export.arxiv.org, github.com, gseapy.readthedocs.io, maayanlab.cloud, mygene.info, pypi.org, www.ensembl.org, www.gsea-msigdb.org | none |
| primekg | PASS | yes | none | arxiv.org, dataverse.harvard.edu, doi.org, export.arxiv.org, github.com, guides.dataverse.org, pypi.org, tdcommons.ai, zitniklab.hms.harvard.edu | PRIMEKG_DATA, PWD |
| pydeseq2 | PASS | yes | none | arxiv.org, bioconductor.org, doi.org, export.arxiv.org, formulaic-contrasts.readthedocs.io, github.com, pydeseq2.readthedocs.io, pypi.org, raw.githubusercontent.com | none |
| pylabrobot | PASS | yes | none | 127.0.0.1, api.github.com, arxiv.org, docs.opentrons.com, docs.pylabrobot.org, doi.org, export.arxiv.org, github.com, json-schema.org, localhost, pypi.org | none |
| pysam | PASS | yes | none | arxiv.org, doi.org, example.org, export.arxiv.org, github.com, header.info, pypi.org, pysam.readthedocs.io, record.info, samtools.github.io, variants.header.info, www.htslib.org | none |
| pytdc | PASS | yes | none | arxiv.org, datasets-benchmarks-proceedings.neurips.cc, dataverse.harvard.edu, doi.org, export.arxiv.org, github.com, guides.dataverse.org, pypi.org, setuptools.pypa.io, tdc.readthedocs.io, tdcommons.ai | none |
| rdkit | PASS | yes | none | arxiv.org, doi.org, export.arxiv.org, github.com, pypi.org, www.rdkit.org | none |
| rowan | PASS | yes | none | api.rowansci.com, docs.rowansci.com, example.org, pypi.org, rowansci.com, www.rcsb.org | ROWAN_API_KEY, ROWAN_WEBHOOK_SECRET |
| scanpy | PASS | yes | none | anndata.io, anndata.readthedocs.io, arxiv.org, cloud.r-project.org, cran.r-project.org, docs.dask.org, doi.org, export.arxiv.org, formulae.brew.sh, github.com, mac.R-project.org, mojaveazure.github.io, rapids-singlecell.readthedocs.io, satijalab.github.io, satijalab.org, scanpy.readthedocs.io, scanpy.scverse.org, scipy.io, scverse.org, theislab.github.io, www.bioconductor.org, www.r-project.org | PWD |
| scvi-tools | PASS | yes | none | arxiv.org, docs.scvi-tools.org, doi.org, export.arxiv.org, github.com, scviva-tools.readthedocs.io | none |
| torchdrug | PASS | yes | none | arxiv.org, data.pyg.org, deepchemdata.s3-us-west-1.amazonaws.com, dl.fbaipublicfiles.com, docs.astral.sh, doi.org, export.arxiv.org, github.com, pypi.org, torchdrug.ai | none |

## Complete excluded list

| Skill | Scan | Reasons |
|---|---|---|
| 13c-metabolic-flux | PASS | outside the scoped candidate list |
| aeon | PASS | outside the scoped candidate list |
| analytical-method-validation | PASS | outside the scoped candidate list |
| arbor | FAIL | LLM-provider key reference/read instruction; outside the scoped candidate list |
| arboreto | PASS | outside the scoped candidate list |
| astropy | PASS | outside the scoped candidate list |
| autoskill | FAIL | LLM-provider key reference/read instruction; cookie, keychain, SSH or screen access; explicit exclusion: screen recordings; outside the scoped candidate list |
| benchling-integration | PASS | outside the scoped candidate list |
| bgpt-paper-search | PASS | outside the scoped candidate list |
| bids | PASS | outside the scoped candidate list |
| bioservices | PASS | outside the scoped candidate list |
| bulk-rnaseq | PASS | outside the scoped candidate list |
| cantera | PASS | outside the scoped candidate list |
| cellprofiler | PASS | outside the scoped candidate list |
| cirq | PASS | outside the scoped candidate list |
| citation-management | FAIL | explicit exclusion: retained explicit exclusion from the supplied review; no provider-key match at this pin; outside the scoped candidate list |
| clinical-decision-support | PASS | outside the scoped candidate list |
| clinical-reports | PASS | outside the scoped candidate list |
| cobrapy | PASS | outside the scoped candidate list |
| consciousness-council | PASS | outside the scoped candidate list |
| dask | PASS | outside the scoped candidate list |
| datalad | FAIL | cookie, keychain, SSH or screen access; outside the scoped candidate list |
| deepspot-m | PASS | outside the scoped candidate list |
| deeptools | PASS | outside the scoped candidate list |
| dhdna-profiler | PASS | outside the scoped candidate list |
| dnanexus-integration | PASS | outside the scoped candidate list |
| etetoolkit | FAIL | cookie, keychain, SSH or screen access; outside the scoped candidate list |
| exa-search | FAIL | LLM-provider key reference/read instruction; outside the scoped candidate list |
| experimental-design | PASS | outside the scoped candidate list |
| exploratory-data-analysis | PASS | outside the scoped candidate list |
| fictiv | FAIL | cookie, keychain, SSH or screen access; outside the scoped candidate list |
| flowio | PASS | outside the scoped candidate list |
| flowkit | PASS | outside the scoped candidate list |
| fluidsim | PASS | outside the scoped candidate list |
| folklore-variant-evidence | PASS | outside the scoped candidate list |
| generate-image | FAIL | LLM-provider key reference/read instruction; outside the scoped candidate list |
| geniml | PASS | outside the scoped candidate list |
| genomic-coordinates | PASS | outside the scoped candidate list |
| genomic-intelligence | PASS | outside the scoped candidate list |
| geomaster | PASS | outside the scoped candidate list |
| geopandas | PASS | outside the scoped candidate list |
| get-available-resources | PASS | outside the scoped candidate list |
| gget | FAIL | LLM-provider key reference/read instruction |
| ginkgo-cloud-lab | PASS | outside the scoped candidate list |
| glycoengineering | PASS | outside the scoped candidate list |
| gtars | PASS | outside the scoped candidate list |
| histolab | PASS | outside the scoped candidate list |
| hugging-science | PASS | outside the scoped candidate list |
| hypogenic | FAIL | LLM-provider key reference/read instruction; outside the scoped candidate list |
| hypothesis-generation | PASS | outside the scoped candidate list |
| imaging-data-commons | PASS | outside the scoped candidate list |
| infographics | FAIL | LLM-provider key reference/read instruction; outside the scoped candidate list |
| iso-standards-readiness | PASS | outside the scoped candidate list |
| lab-hardware-cad | PASS | outside the scoped candidate list |
| labarchive-integration | FAIL | cookie, keychain, SSH or screen access; outside the scoped candidate list |
| lamindb | PASS | outside the scoped candidate list |
| latex-posters | FAIL | LLM-provider key reference/read instruction; outside the scoped candidate list |
| liteparse | PASS | outside the scoped candidate list |
| literature-review | FAIL | LLM-provider key reference/read instruction; outside the scoped candidate list |
| mageck | PASS | outside the scoped candidate list |
| marine-carbonate-chemistry | PASS | outside the scoped candidate list |
| markdown-mermaid-writing | FAIL | cookie, keychain, SSH or screen access; outside the scoped candidate list |
| market-research-reports | PASS | outside the scoped candidate list |
| markitdown | FAIL | LLM-provider key reference/read instruction; cookie, keychain, SSH or screen access; outside the scoped candidate list |
| matchms | PASS | outside the scoped candidate list |
| matlab | PASS | outside the scoped candidate list |
| matplotlib | PASS | outside the scoped candidate list |
| modal | FAIL | LLM-provider key reference/read instruction; outside the scoped candidate list |
| molecular-dynamics | PASS | outside the scoped candidate list |
| ncats-arax | PASS | outside the scoped candidate list |
| networkx | PASS | outside the scoped candidate list |
| neurokit2 | PASS | outside the scoped candidate list |
| neuropixels-analysis | FAIL | LLM-provider key reference/read instruction; outside the scoped candidate list |
| nextflow | FAIL | fetches and runs remote code; outside the scoped candidate list |
| nmrglue | PASS | outside the scoped candidate list |
| nwb-conversion | PASS | outside the scoped candidate list |
| omero-integration | FAIL | cookie, keychain, SSH or screen access; outside the scoped candidate list |
| onekgpd | PASS | outside the scoped candidate list |
| ontology-term-resolution | PASS | outside the scoped candidate list |
| open-notebook | FAIL | LLM-provider key reference/read instruction; outside the scoped candidate list |
| openpiv | PASS | outside the scoped candidate list |
| optimize-for-gpu | PASS | outside the scoped candidate list |
| pacsomatic | PASS | outside the scoped candidate list |
| paper-lookup | PASS | outside the scoped candidate list |
| paperclip | FAIL | cookie, keychain, SSH or screen access; pipe-to-shell installation; explicit exclusion: browser cookies, uploads and pipe-to-shell installation; outside the scoped candidate list |
| paperzilla | PASS | outside the scoped candidate list |
| parallel-web | FAIL | LLM-provider key reference/read instruction; outside the scoped candidate list |
| pathml | PASS | outside the scoped candidate list |
| pathogen-variant-surveillance | PASS | outside the scoped candidate list |
| peer-review | PASS | outside the scoped candidate list |
| pennylane | PASS | outside the scoped candidate list |
| phylogenetics | PASS | outside the scoped candidate list |
| pi-agent | FAIL | LLM-provider key reference/read instruction; cookie, keychain, SSH or screen access; pipe-to-shell installation; settings or hook instruction; explicit exclusion: pipe-to-shell installation; outside the scoped candidate list |
| pkpd-modeling | PASS | outside the scoped candidate list |
| polars | PASS | outside the scoped candidate list |
| polars-bio | PASS | outside the scoped candidate list |
| pptx-posters | PASS | outside the scoped candidate list |
| primer-design | PASS | outside the scoped candidate list |
| protocolsio-integration | PASS | outside the scoped candidate list |
| pufferlib | PASS | outside the scoped candidate list |
| pybamm | PASS | outside the scoped candidate list |
| pycalphad | PASS | outside the scoped candidate list |
| pydicom | PASS | outside the scoped candidate list |
| pyhealth | PASS | outside the scoped candidate list |
| pymatgen | PASS | outside the scoped candidate list |
| pymc | PASS | outside the scoped candidate list |
| pymoo | PASS | outside the scoped candidate list |
| pyopenms | PASS | outside the scoped candidate list |
| pytorch-lightning | PASS | outside the scoped candidate list |
| pyzotero | PASS | outside the scoped candidate list |
| qiime2-amplicon | PASS | outside the scoped candidate list |
| qiskit | PASS | outside the scoped candidate list |
| qutip | PASS | outside the scoped candidate list |
| relion | PASS | outside the scoped candidate list |
| relsa-severity-assessment | PASS | outside the scoped candidate list |
| research-grants | FAIL | LLM-provider key reference/read instruction; outside the scoped candidate list |
| research-lookup | FAIL | LLM-provider key reference/read instruction; outside the scoped candidate list |
| scholar-evaluation | PASS | outside the scoped candidate list |
| scientific-brainstorming | PASS | outside the scoped candidate list |
| scientific-critical-thinking | FAIL | LLM-provider key reference/read instruction; outside the scoped candidate list |
| scientific-schematics | FAIL | LLM-provider key reference/read instruction; outside the scoped candidate list |
| scientific-slides | FAIL | LLM-provider key reference/read instruction; outside the scoped candidate list |
| scientific-visualization | PASS | outside the scoped candidate list |
| scientific-writing | PASS | outside the scoped candidate list |
| scikit-bio | PASS | outside the scoped candidate list |
| scikit-learn | PASS | outside the scoped candidate list |
| scikit-survival | PASS | outside the scoped candidate list |
| scvelo | PASS | outside the scoped candidate list |
| seaborn | PASS | outside the scoped candidate list |
| shap | PASS | outside the scoped candidate list |
| simpy | PASS | outside the scoped candidate list |
| stable-baselines3 | PASS | outside the scoped candidate list |
| statistical-analysis | PASS | outside the scoped candidate list |
| statistical-power | PASS | outside the scoped candidate list |
| statsmodels | PASS | outside the scoped candidate list |
| sympy | PASS | outside the scoped candidate list |
| tamarind | PASS | outside the scoped candidate list |
| tellurium | PASS | outside the scoped candidate list |
| tiledbvcf | PASS | outside the scoped candidate list |
| timesfm-forecasting | PASS | outside the scoped candidate list |
| torch-geometric | PASS | outside the scoped candidate list |
| transformers | PASS | outside the scoped candidate list |
| treatment-plans | PASS | outside the scoped candidate list |
| umap-learn | PASS | outside the scoped candidate list |
| uncertainty-and-units | PASS | outside the scoped candidate list |
| usfiscaldata | PASS | outside the scoped candidate list |
| vaex | PASS | outside the scoped candidate list |
| venue-templates | PASS | outside the scoped candidate list |
| waypoint-bio | FAIL | fetches and runs remote code; outside the scoped candidate list |
| what-if-oracle | PASS | outside the scoped candidate list |
| zarr-python | PASS | outside the scoped candidate list |

## Candidate file evidence

Every candidate file is listed, including files with no matches. Each entry records the matched category, line and token; downloaded instructions are evidence, never instructions for this tool.

### adaptyv

- [SKILL.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/adaptyv/SKILL.md):
  - env: 31: ADAPTYV_API_KEY; 37: ADAPTYV_API_KEY; 39: ADAPTYV_API_KEY; 55: ADAPTYV_API_KEY; 72: ADAPTYV_API_KEY; 86: ADAPTYV_TARGET_ID; 145: ADAPTYV_EXPERIMENT_ID; 148: ADAPTYV_API_KEY
  - environment_access: 33: load_dotenv; 72: os.environ; 86: os.environ; 145: os.environ; 148: os.environ
  - hosts: 18: devs.adaptyvbio.com; 26: devs.adaptyvbio.com; 29: foundry.adaptyvbio.com; 38: devs.adaptyvbio.com; 51: github.com; 73: devs.adaptyvbio.com; 147: devs.adaptyvbio.com; 268: doi.org; 270: arxiv.org; 272: arxiv.org; 273: export.arxiv.org
  - install: 51: uv pip install
  - shell: 36: \`\`\`bash; 50: \`\`\`bash
  - urls: 18: https://devs.adaptyvbio.com/api/v1/openapi.json; 26: https://devs.adaptyvbio.com/api/v1; 29: https://foundry.adaptyvbio.com/; 38: https://devs.adaptyvbio.com/api/v1/targets?limit=3; 51: git+https://github.com/adaptyvbio/adaptyv-sdk.git@cdf207819ed5a58e0c127453626d2bce125c8064; 73: https://devs.adaptyvbio.com/api/v1; 147: https://devs.adaptyvbio.com/api/v1; 268: https://doi.org/10.48550/arXiv.2609.00065; 270: https://arxiv.org/abs/2609.00065; 272: https://arxiv.org/abs/2609.00065; 273: http://export.arxiv.org/api/query?id_list=2609.00065
- [references/api-endpoints.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/adaptyv/references/api-endpoints.md):
  - hosts: 4: devs.adaptyvbio.com; 5: docs.adaptyvbio.com; 6: github.com; 7: devs.adaptyvbio.com
  - urls: 4: https://devs.adaptyvbio.com/api/v1/openapi.json; 5: https://docs.adaptyvbio.com/api-reference/api-introduction; 6: https://github.com/adaptyvbio/adaptyv-sdk/tree/cdf207819ed5a58e0c127453626d2bce125c8064; 7: https://devs.adaptyvbio.com/api/v1

### alphagenome

- [SKILL.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/alphagenome/SKILL.md):
  - env: 5: ALPHAGENOME_API_KEY; 5: ALPHA_GENOME_API_KEY; 13: ALPHAGENOME_API_KEY; 15: ALPHAGENOME_API_KEY; 17: ALPHA_GENOME_API_KEY; 49: ALPHAGENOME_API_KEY; 152: ALPHAGENOME_API_KEY; 193: ALPHAGENOME_API_KEY
  - environment_access: 152: os.environ; 193: os.environ
  - hosts: 5: gdmscience.googleapis.com:443; 17: deepmind.google.com; 49: deepmind.google.com; 256: alphagenome.google; 261: www.alphagenomedocs.com; 290: doi.org; 292: arxiv.org; 294: arxiv.org; 295: export.arxiv.org
  - install: 28: pip install; 48: uv pip install
  - shell: 47: \`\`\`bash; 83: \`\`\`bash; 116: \`\`\`bash; 135: \`\`\`bash; 174: \`\`\`bash
  - urls: 49: https://deepmind.google.com/science/alphagenome; 256: https://alphagenome.google/downloads; 261: https://www.alphagenomedocs.com/faqs.html; 290: https://doi.org/10.48550/arXiv.2609.00065; 292: https://arxiv.org/abs/2609.00065; 294: https://arxiv.org/abs/2609.00065; 295: http://export.arxiv.org/api/query?id_list=2609.00065
- [references/atlas.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/alphagenome/references/atlas.md):
  - hosts: 11: doi.org; 130: gdmscience.googleapis.com:443; 214: alphagenome.google; 220: docs.cloud.google.com; 230: deepmind.google.com; 231: alphagenome.google; 250: storage.googleapis.com; 255: alphagenome.google; 263: github.com; 268: pypi.org; 269: github.com; 270: github.com; 271: github.com; 272: github.com; 273: github.com; 274: www.alphagenomedocs.com; 275: deepmind.google
  - urls: 11: https://doi.org/10.64898/2026.09.16.26363192; 214: https://alphagenome.google/downloads; 220: https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/open-models/alphagenome; 230: https://deepmind.google.com/science/alphagenome/atlas; 231: https://alphagenome.google/atlas; 250: https://storage.googleapis.com/alphagenome/reference/gencode/hg38/gencode.v46.annotation.gtf.gz.feather; 255: https://alphagenome.google/downloads; 263: https://github.com/google-deepmind/alphagenome; 268: https://pypi.org/project/alphagenome/0.9.0/; 269: https://github.com/google-deepmind/alphagenome/blob/main/src/alphagenome/atlas/atlas.py; 270: https://github.com/google-deepmind/alphagenome/blob/main/src/alphagenome/protos/atlas_service.proto; 271: https://github.com/google-deepmind/alphagenome/blob/main/src/alphagenome/atlas/atlas_utils.py; 272: https://github.com/google-deepmind/alphagenome/blob/main/src/alphagenome/protos/grpc_service_config.json; 273: https://github.com/google-deepmind/science-skills/tree/main/skills/alphagenome_atlas_website_links; 274: https://www.alphagenomedocs.com/faqs.html; 275: https://deepmind.google/blog/alphagenome-atlas-a-predictive-map-of-every-possible-dna-letter-change-in-the-human-genome/
- [references/interpretation.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/alphagenome/references/interpretation.md):
  - hosts: 49: www.alphagenomedocs.com; 50: www.alphagenomedocs.com
  - urls: 49: https://www.alphagenomedocs.com/variant_scoring.html; 50: https://www.alphagenomedocs.com/faqs.html
- [references/model-api.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/alphagenome/references/model-api.md):
  - env: 12: ALPHAGENOME_API_KEY; 21: ALPHAGENOME_API_KEY; 24: ALPHA_GENOME_API_KEY
  - environment_access: 21: os.environ
  - hosts: 12: deepmind.google.com; 203: storage.googleapis.com; 245: www.alphagenomedocs.com; 248: github.com; 249: github.com; 251: github.com; 257: gdmscience.googleapis.com:443; 267: github.com; 268: www.alphagenomedocs.com; 269: www.alphagenomedocs.com; 270: www.alphagenomedocs.com; 271: github.com
  - install: 11: uv pip install
  - shell: 10: \`\`\`bash
  - urls: 12: https://deepmind.google.com/science/alphagenome; 203: https://storage.googleapis.com/alphagenome/reference/gencode/hg38/gencode.v46.annotation.gtf.gz.feather; 245: https://www.alphagenomedocs.com/; 248: https://github.com/google-deepmind/alphagenome; 249: https://github.com/google-deepmind/alphagenome_research; 251: https://github.com/google-deepmind/science-skills; 267: https://github.com/google-deepmind/alphagenome; 268: https://www.alphagenomedocs.com/variant_scoring.html; 269: https://www.alphagenomedocs.com/exploring_model_metadata.html; 270: https://www.alphagenomedocs.com/faqs.html; 271: https://github.com/google-deepmind/alphagenome_research/blob/main/src/alphagenome_research/model/variant_scoring/gene_mask.py
- [scripts/_common.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/alphagenome/scripts/_common.py):
  - env: 29: ALPHAGENOME_API_KEY; 29: ALPHA_GENOME_API_KEY
  - environment_access: 367: os.environ.get
  - hosts: 31: deepmind.google.com; 32: deepmind.google.com; 34: www.alphagenomedocs.com; 39: storage.googleapis.com
  - install: 98: uv pip install
  - urls: 31: https://deepmind.google.com/science/alphagenome; 32: https://deepmind.google.com/science/alphagenome/atlas; 34: https://www.alphagenomedocs.com/; 39: https://storage.googleapis.com/alphagenome/reference/gencode/hg38/
- [scripts/atlas_link.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/alphagenome/scripts/atlas_link.py):
  - hosts: 4: deepmind.google.com
  - urls: 4: https://deepmind.google.com/science/alphagenome/atlas
- [scripts/atlas_query.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/alphagenome/scripts/atlas_query.py):
  - env: 23: ALPHAGENOME_API_KEY; 23: ALPHA_GENOME_API_KEY; 478: ALPHAGENOME_API_KEY; 478: ALPHA_GENOME_API_KEY
  - hosts: 266: gdmscience.googleapis.com:443
- [scripts/score_variants.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/alphagenome/scripts/score_variants.py):
  - env: 217: ALPHAGENOME_API_KEY; 217: ALPHA_GENOME_API_KEY
  - hosts: 98: gdmscience.googleapis.com:443

### anndata

- [SKILL.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/anndata/SKILL.md):
  - hosts: 48: anndata.io; 54: anndata.readthedocs.io; 92: anndata.io; 93: anndata.io; 159: anndata.io; 324: anndata.readthedocs.io; 394: anndata.readthedocs.io; 394: anndata.io; 454: anndata.readthedocs.io; 455: scanpy.readthedocs.io; 456: scverse.org; 457: github.com; 467: doi.org; 469: arxiv.org; 471: arxiv.org; 472: export.arxiv.org
  - install: 39: uv pip install; 42: uv pip install
  - shell: 38: \`\`\`bash
  - urls: 54: https://anndata.readthedocs.io/en/stable/release-notes/; 324: https://anndata.readthedocs.io/en/stable/tutorials/notebooks/annbatch.html; 394: https://anndata.readthedocs.io/en/stable/generated/anndata.io.read_h5ad.html; 454: https://anndata.readthedocs.io/; 455: https://scanpy.readthedocs.io/; 456: https://scverse.org/; 457: https://github.com/scverse/anndata; 467: https://doi.org/10.48550/arXiv.2609.00065; 469: https://arxiv.org/abs/2609.00065; 471: https://arxiv.org/abs/2609.00065; 472: http://export.arxiv.org/api/query?id_list=2609.00065
- [references/best_practices.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/anndata/references/best_practices.md):
  - hosts: 426: anndata.readthedocs.io; 546: anndata.readthedocs.io; 547: anndata.readthedocs.io; 548: anndata.readthedocs.io; 549: anndata.readthedocs.io; 549: anndata.io
  - urls: 426: https://anndata.readthedocs.io/en/stable/tutorials/notebooks/annbatch.html; 546: https://anndata.readthedocs.io/en/stable/release-notes/; 547: https://anndata.readthedocs.io/en/stable/generated/anndata.AnnData.raw.html; 548: https://anndata.readthedocs.io/en/stable/generated/anndata.AnnData.write_csvs.html; 549: https://anndata.readthedocs.io/en/stable/generated/anndata.io.read_h5ad.html
- [references/concatenation.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/anndata/references/concatenation.md):
  - hosts: 417: anndata.readthedocs.io; 418: anndata.readthedocs.io; 419: anndata.readthedocs.io; 420: anndata.readthedocs.io
  - urls: 417: https://anndata.readthedocs.io/en/stable/generated/anndata.concat.html; 418: https://anndata.readthedocs.io/en/stable/generated/anndata.experimental.AnnCollection.html; 419: https://anndata.readthedocs.io/en/stable/generated/anndata.experimental.AnnCollection.to_adata.html; 420: https://anndata.readthedocs.io/en/stable/generated/anndata.experimental.concat_on_disk.html
- [references/data_structure.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/anndata/references/data_structure.md):
  - hosts: 324: anndata.readthedocs.io
  - urls: 324: https://anndata.readthedocs.io/en/stable/generated/anndata.AnnData.html; 324: https://anndata.readthedocs.io/en/stable/generated/anndata.AnnData.raw.html; 324: https://anndata.readthedocs.io/en/stable/fileformat-prose.html; 324: https://anndata.readthedocs.io/en/stable/release-notes/
- [references/io_operations.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/anndata/references/io_operations.md):
  - hosts: 5: anndata.io; 9: anndata.io; 12: anndata.io; 117: anndata.io; 133: anndata.io; 146: anndata.io; 186: anndata.io; 201: anndata.io; 217: anndata.io; 225: anndata.io; 265: anndata.io; 277: anndata.io; 317: anndata.io; 491: anndata.readthedocs.io; 492: anndata.readthedocs.io; 492: anndata.io; 493: anndata.readthedocs.io; 493: anndata.io; 494: anndata.readthedocs.io; 495: anndata.readthedocs.io; 496: anndata.readthedocs.io
  - urls: 109: s3://bucket-name/data.zarr; 491: https://anndata.readthedocs.io/en/stable/api.html; 492: https://anndata.readthedocs.io/en/stable/generated/anndata.io.read_h5ad.html; 493: https://anndata.readthedocs.io/en/stable/generated/anndata.io.read_mtx.html; 494: https://anndata.readthedocs.io/en/stable/generated/anndata.experimental.read_lazy.html; 495: https://anndata.readthedocs.io/en/stable/generated/anndata.AnnData.write_csvs.html; 496: https://anndata.readthedocs.io/en/stable/fileformat-prose.html
- [references/manipulation.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/anndata/references/manipulation.md):
  - hosts: 546: anndata.readthedocs.io
  - urls: 546: https://anndata.readthedocs.io/en/stable/generated/anndata.AnnData.html; 546: https://anndata.readthedocs.io/en/stable/generated/anndata.AnnData.rename_categories.html; 546: https://anndata.readthedocs.io/en/stable/generated/anndata.AnnData.chunked_X.html; 546: https://anndata.readthedocs.io/en/stable/release-notes/

### biopython

- [SKILL.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/biopython/SKILL.md):
  - env: 16: NCBI_API_KEY; 64: NCBI_API_KEY; 74: NCBI_API_KEY; 283: NCBI_API_KEY; 290: NCBI_API_KEY
  - environment_access: 74: os.environ.get; 290: os.environ.get
  - hosts: 25: github.com; 70: example.com; 73: www.ncbi.nlm.nih.gov; 142: example.com; 167: example.com; 288: example.com; 329: example.com; 363: example.com; 435: pypi.org; 442: biopython.org; 443: biopython.org; 444: biopython.org; 445: github.com; 446: github.com; 447: github.com; 448: biopython.org; 473: doi.org; 475: arxiv.org; 477: arxiv.org; 478: export.arxiv.org
  - install: 61: uv pip install
  - shell: 60: \`\`\`bash; 262: \`\`\`bash; 435: subprocess; 454: \`\`\`bash
  - urls: 25: https://github.com/biopython/biopython/blob/biopython-188/NEWS.rst; 73: https://www.ncbi.nlm.nih.gov/account/settings/; 435: https://pypi.org/project/hmmlearn/; 442: https://biopython.org/docs/latest/; 443: https://biopython.org/docs/latest/Tutorial/; 444: https://biopython.org/docs/latest/Tutorial/; 445: https://github.com/biopython/biopython; 446: https://github.com/biopython/biopython/blob/master/NEWS.rst; 447: https://github.com/biopython/biopython/blob/master/DEPRECATED.rst; 473: https://doi.org/10.48550/arXiv.2609.00065; 475: https://arxiv.org/abs/2609.00065; 477: https://arxiv.org/abs/2609.00065; 478: http://export.arxiv.org/api/query?id_list=2609.00065
- [references/advanced.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/biopython/references/advanced.md):
  - hosts: 319: pypi.org; 345: example.com
  - urls: 319: https://pypi.org/project/hmmlearn/
- [references/alignment.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/biopython/references/alignment.md):
  - shell: 279: subprocess; 281: subprocess; 284: subprocess; 296: subprocess.run; 302: subprocess; 305: subprocess; 314: subprocess.run
- [references/blast.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/biopython/references/blast.md):
  - hosts: 11: blast.ncbi.nlm.nih.gov; 26: example.com; 283: example.com; 399: example.com
  - shell: 189: subprocess; 191: subprocess; 194: subprocess; 205: subprocess.run; 224: subprocess; 232: subprocess.run; 312: subprocess; 321: subprocess.run; 340: subprocess; 350: subprocess.run
  - urls: 11: https://blast.ncbi.nlm.nih.gov/Blast.cgi
- [references/databases.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/biopython/references/databases.md):
  - env: 26: NCBI_API_KEY; 31: NCBI_API_KEY; 32: NCBI_API_KEY; 421: NCBI_API_KEY
  - environment_access: 32: os.environ.get
  - hosts: 17: example.com; 26: www.ncbi.nlm.nih.gov; 437: example.com; 456: example.com
  - urls: 26: https://www.ncbi.nlm.nih.gov/account/settings/
- [references/phylogenetics.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/biopython/references/phylogenetics.md): no matches
- [references/review.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/biopython/references/review.md):
  - hosts: 6: github.com; 7: github.com; 12: eutils.ncbi.nlm.nih.gov; 33: biopython.org; 34: github.com; 35: ncbiinsights.ncbi.nlm.nih.gov; 36: www.ncbi.nlm.nih.gov; 40: blast.ncbi.nlm.nih.gov; 45: blast.ncbi.nlm.nih.gov; 46: blast.ncbi.nlm.nih.gov; 47: biopython.org; 52: biopython.org; 71: www.drive5.com; 74: biopython.org; 78: biopython.org; 79: biopython.org; 80: biopython.org; 81: biopython.org; 82: biopython.org; 83: biopython.org; 84: biopython.org; 85: biopython.org; 86: github.com; 87: biopython.org
  - urls: 6: https://github.com/biopython/biopython/blob/biopython-188/NEWS.rst; 7: https://github.com/biopython/biopython/blob/biopython-188/DEPRECATED.rst; 12: https://eutils.ncbi.nlm.nih.gov/entrez/eutils/; 33: https://biopython.org/docs/latest/api/Bio.Entrez.html; 34: https://github.com/biopython/biopython/blob/biopython-188/Bio/Entrez/__init__.py; 35: https://ncbiinsights.ncbi.nlm.nih.gov/2022/11/22/updated-pubmed-eutilities-live/; 36: https://www.ncbi.nlm.nih.gov/entrez/query/static/entrezlinks.html; 40: https://blast.ncbi.nlm.nih.gov/Blast.cgi; 45: https://blast.ncbi.nlm.nih.gov/doc/blast-help/urlapi.html; 46: https://blast.ncbi.nlm.nih.gov/doc/blast-help/developerinfo.html; 47: https://biopython.org/docs/latest/api/Bio.Blast.NCBIXML.html; 52: https://biopython.org/docs/latest/api/Bio.PDB.PDBList.html; 71: https://www.drive5.com/muscle5/manual/cmd_align.html; 74: https://biopython.org/docs/latest/api/Bio.PDB.DSSP.html; 78: https://biopython.org/docs/latest/Tutorial/chapter_seqio.html; 79: https://biopython.org/docs/latest/api/Bio.SeqRecord.html; 80: https://biopython.org/docs/latest/api/Bio.SeqFeature.html; 81: https://biopython.org/docs/latest/Tutorial/chapter_pairwise.html; 82: https://biopython.org/docs/latest/api/Bio.Phylo.BaseTree.html; 83: https://biopython.org/docs/latest/api/Bio.Phylo.TreeConstruction.html; 84: https://biopython.org/docs/latest/Tutorial/chapter_pdb.html; 85: https://biopython.org/docs/latest/api/Bio.SeqUtils.html; 86: https://github.com/biopython/biopython/blob/biopython-188/Bio/SeqUtils/ProtParam.py; 87: https://biopython.org/docs/latest/Tutorial/chapter_motifs.html
- [references/sequence_io.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/biopython/references/sequence_io.md): no matches
- [references/structure.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/biopython/references/structure.md): no matches

### cellxgene-census

- [SKILL.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/cellxgene-census/SKILL.md):
  - hosts: 327: doi.org; 329: arxiv.org; 331: arxiv.org; 332: export.arxiv.org
  - install: 43: uv pip install; 48: uv pip install; 54: uv pip install
  - shell: 42: \`\`\`bash; 47: \`\`\`bash; 53: \`\`\`bash
  - urls: 327: https://doi.org/10.48550/arXiv.2609.00065; 329: https://arxiv.org/abs/2609.00065; 331: https://arxiv.org/abs/2609.00065; 332: http://export.arxiv.org/api/query?id_list=2609.00065
- [references/api_access.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/cellxgene-census/references/api_access.md):
  - hosts: 16: census.cellxgene.cziscience.com; 17: census.cellxgene.cziscience.com; 20: contrib.cellxgene.cziscience.com; 97: chanzuckerberg.github.io; 98: pypi.org; 99: chanzuckerberg.github.io; 100: chanzuckerberg.github.io; 101: github.com; 102: chanzuckerberg.github.io; 103: single-cell-data.github.io; 104: chanzuckerberg.github.io; 105: scanpy.readthedocs.io
  - urls: 16: https://census.cellxgene.cziscience.com/cellxgene-census/v1/release.json; 17: https://census.cellxgene.cziscience.com/cellxgene-census/v1/mirrors.json; 18: s3://cellxgene-census-public-us-west-2/cell-census/2025-11-08/soma/; 20: https://contrib.cellxgene.cziscience.com/contrib/cell-census/contributions.json; 97: https://chanzuckerberg.github.io/cellxgene-census/python-api.html; 98: https://pypi.org/project/cellxgene-census/1.18.0/; 99: https://chanzuckerberg.github.io/cellxgene-census/cellxgene_census_docsite_data_release_info.html; 100: https://chanzuckerberg.github.io/cellxgene-census/cellxgene_census_docsite_installation.html; 101: https://github.com/chanzuckerberg/cellxgene-census/blob/main/docs/cellxgene_census_schema.md; 102: https://chanzuckerberg.github.io/cellxgene-census/notebooks/api_demo/census_spatial.html; 103: https://single-cell-data.github.io/TileDB-SOMA-ML/; 104: https://chanzuckerberg.github.io/cellxgene-census/_autosummary/cellxgene_census.experimental.pp.mean_variance.html; 105: https://scanpy.readthedocs.io/en/stable/generated/scanpy.external.pp.scanorama_integrate.html
- [references/census_schema.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/cellxgene-census/references/census_schema.md):
  - hosts: 13: github.com; 13: chanzuckerberg.github.io
  - urls: 13: https://github.com/chanzuckerberg/cellxgene-census/blob/main/docs/cellxgene_census_schema.md; 13: https://chanzuckerberg.github.io/cellxgene-census/cellxgene_census_docsite_data_release_info.html
- [references/common_patterns.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/cellxgene-census/references/common_patterns.md): no matches
- [references/core_workflow_patterns.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/cellxgene-census/references/core_workflow_patterns.md): no matches

### database-lookup

- [SKILL.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/SKILL.md):
  - env: 116: FRED_API_KEY; 117: BEA_API_KEY; 118: BLS_API_KEY; 119: NCBI_API_KEY; 120: OPENFDA_API_KEY; 121: USPTO_ODP_API_KEY; 122: DATACOMMONS_API_KEY; 123: MP_API_KEY; 124: NASA_API_KEY; 125: NOAA_API_KEY; 126: OPENWEATHERMAP_API_KEY; 127: OMIM_API_KEY; 128: BIOGRID_API_KEY; 129: ALPHAVANTAGE_API_KEY; 130: CENSUS_API_KEY; 131: DISGENET_API_KEY; 132: ADDGENE_API_KEY; 133: CLUE_API_KEY; 154: FRED_API_KEY
  - hosts: 96: api.platform.opentargets.org; 97: gnomad.broadinstitute.org; 98: rummageo.com; 116: fred.stlouisfed.org; 117: apps.bea.gov; 118: data.bls.gov; 119: www.ncbi.nlm.nih.gov; 120: open.fda.gov; 121: data.uspto.gov; 122: apikeys.datacommons.org; 123: materialsproject.org; 124: api.nasa.gov; 125: www.ncdc.noaa.gov; 126: openweathermap.org; 127: omim.org; 128: webservice.thebiogrid.org; 129: www.alphavantage.co; 130: api.census.gov; 131: www.disgenet.com; 132: developers.addgene.org; 133: clue.io; 169: rest.uniprot.org; 205: ClinicalTrials.gov; 331: MyVariant.info; 348: ClinicalTrials.gov; 392: doi.org; 394: arxiv.org; 396: arxiv.org; 397: export.arxiv.org
  - shell: 153: \`\`\`bash; 166: \`\`\`bash
  - urls: 96: https://api.platform.opentargets.org/api/v4/graphql; 97: https://gnomad.broadinstitute.org/api; 98: https://rummageo.com/graphql; 116: https://fred.stlouisfed.org/docs/api/api_key.html; 117: https://apps.bea.gov/API/signup/; 118: https://data.bls.gov/registrationEngine/; 119: https://www.ncbi.nlm.nih.gov/account/settings/; 120: https://open.fda.gov/apis/authentication/; 121: https://data.uspto.gov/apikey; 122: https://apikeys.datacommons.org; 123: https://materialsproject.org; 124: https://api.nasa.gov; 125: https://www.ncdc.noaa.gov/cdo-web/token; 126: https://openweathermap.org/appid; 127: https://omim.org/api; 128: https://webservice.thebiogrid.org; 129: https://www.alphavantage.co/support/#api-key; 130: https://api.census.gov/data/key_signup.html; 131: https://www.disgenet.com; 132: https://developers.addgene.org; 133: https://clue.io; 169: https://rest.uniprot.org/uniprotkb/P04637.json; 392: https://doi.org/10.48550/arXiv.2609.00065; 394: https://arxiv.org/abs/2609.00065; 396: https://arxiv.org/abs/2609.00065; 397: http://export.arxiv.org/api/query?id_list=2609.00065
- [references/addgene.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/addgene.md):
  - env: 7: ADDGENE_API_KEY; 29: ADDGENE_API_KEY
  - hosts: 5: api.developers.addgene.org; 28: api.developers.addgene.org; 39: docs.developers.addgene.org; 40: developers.addgene.org
  - shell: 27: \`\`\`bash
  - urls: 5: https://api.developers.addgene.org; 28: https://api.developers.addgene.org/catalog/plasmid/; 39: https://docs.developers.addgene.org/docs/schema/; 40: https://developers.addgene.org/access-options/
- [references/alphafold.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/alphafold.md):
  - hosts: 5: alphafold.ebi.ac.uk; 23: alphafold.ebi.ac.uk; 24: alphafold.ebi.ac.uk; 25: alphafold.ebi.ac.uk; 26: alphafold.ebi.ac.uk; 27: alphafold.ebi.ac.uk; 28: alphafold.ebi.ac.uk; 34: alphafold.ebi.ac.uk; 37: alphafold.ebi.ac.uk; 38: alphafold.ebi.ac.uk; 41: alphafold.ebi.ac.uk
  - urls: 5: https://alphafold.ebi.ac.uk/api/; 23: https://alphafold.ebi.ac.uk/files/AF-{UNIPROT}-F1-model_v6.pdb; 24: https://alphafold.ebi.ac.uk/files/AF-{UNIPROT}-F1-model_v6.cif; 25: https://alphafold.ebi.ac.uk/files/AF-{UNIPROT}-F1-model_v6.bcif; 26: https://alphafold.ebi.ac.uk/files/AF-{UNIPROT}-F1-predicted_aligned_error_v6.json; 27: https://alphafold.ebi.ac.uk/files/AF-{UNIPROT}-F1-confidence_v6.json; 28: https://alphafold.ebi.ac.uk/files/msa/AF-{UNIPROT}-F1-msa_v6.a3m; 34: https://alphafold.ebi.ac.uk/api/prediction/P00533; 37: https://alphafold.ebi.ac.uk/files/AF-P00533-F1-model_v6.pdb; 38: https://alphafold.ebi.ac.uk/files/AF-P00533-F1-model_v6.cif; 41: https://alphafold.ebi.ac.uk/files/AF-P00533-F1-predicted_aligned_error_v6.json
- [references/alphavantage.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/alphavantage.md):
  - hosts: 8: www.alphavantage.co; 14: www.alphavantage.co; 42: www.alphavantage.co; 99: www.alphavantage.co; 189: www.alphavantage.co; 194: www.alphavantage.co
  - urls: 8: https://www.alphavantage.co/query; 14: https://www.alphavantage.co/support/#api-key; 42: https://www.alphavantage.co/query?function=TIME_SERIES_INTRADAY&symbol=AAPL&interval=5min&apikey=YOUR_KEY; 99: https://www.alphavantage.co/query?function=SYMBOL_SEARCH&keywords=microsoft&apikey=YOUR_KEY; 189: https://www.alphavantage.co/query?function=RSI&symbol=AAPL&interval=daily&time_period=14&series_type=close&apikey=YOUR_KEY; 194: https://www.alphavantage.co/query?function=MACD&symbol=AAPL&interval=daily&series_type=close&apikey=YOUR_KEY
- [references/bea.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/bea.md):
  - env: 13: YOUR_API_KEY
  - hosts: 8: apps.bea.gov; 12: apps.bea.gov; 39: apps.bea.gov; 79: apps.bea.gov; 124: apps.bea.gov; 166: apps.bea.gov; 171: apps.bea.gov; 250: apps.bea.gov; 255: apps.bea.gov; 305: apps.bea.gov; 330: apps.bea.gov; 347: apps.bea.gov; 362: apps.bea.gov; 407: apps.bea.gov; 411: apps.bea.gov
  - urls: 8: https://apps.bea.gov/api/data; 12: https://apps.bea.gov/API/signup/; 39: https://apps.bea.gov/api/data?method=GetDataSetList&UserID=YOUR_KEY&ResultFormat=JSON; 79: https://apps.bea.gov/api/data?method=GetParameterList&DatasetName=NIPA&UserID=YOUR_KEY&ResultFormat=JSON; 124: https://apps.bea.gov/api/data?method=GetParameterValues&DatasetName=NIPA&ParameterName=TableName&UserID=YOUR_KEY&ResultFormat=JSON; 166: https://apps.bea.gov/api/data?method=GetData&DatasetName=NIPA&TableName=T10101&Frequency=Q&Year=2022,2023,2024&UserID=YOUR_KEY&ResultFormat=JSON; 171: https://apps.bea.gov/api/data?method=GetData&DatasetName=NIPA&TableName=T10105&Frequency=A&Year=ALL&UserID=YOUR_KEY&ResultFormat=JSON; 250: https://apps.bea.gov/api/data?method=GetData&DatasetName=Regional&TableName=CAGDP1&LineCode=1&GeoFips=STATE&Year=2020,2021,2022,2023&UserID=YOUR_KEY&ResultFormat=JSON; 255: https://apps.bea.gov/api/data?method=GetData&DatasetName=Regional&TableName=CAINC1&LineCode=1&GeoFips=06000&Year=LAST5&UserID=YOUR_KEY&ResultFormat=JSON; 305: https://apps.bea.gov/api/data?method=GetData&DatasetName=ITA&Indicator=BalGds&AreaOrCountry=China&Frequency=Q&Year=2022,2023,2024&UserID=YOUR_KEY&ResultFormat=JSON; 330: https://apps.bea.gov/api/data?method=GetData&DatasetName=GDPbyIndustry&TableID=1&Industry=ALL&Frequency=A&Year=2020,2021,2022,2023&UserID=YOUR_KEY&ResultFormat=JSON; 347: https://apps.bea.gov/api/data?method=GetData&DatasetName=IIP&TypeOfInvestment=ALL&Component=ALL&Frequency=A&Year=2020,2021,2022,2023&UserID=YOUR_KEY&ResultFormat=JSON; 362: https://apps.bea.gov/api/data?method=GetData&DatasetName=FixedAssets&TableName=FAAt101&Year=ALL&UserID=YOUR_KEY&ResultFormat=JSON; 407: https://apps.bea.gov/iTable/; 411: https://apps.bea.gov/api/_pdf/bea_web_service_api_user_guide.pdf
- [references/bindingdb.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/bindingdb.md):
  - hosts: 5: bindingdb.org; 6: bindingdb.org; 28: bindingdb.org; 36: bindingdb.org; 41: bindingdb.org; 49: bindingdb.org; 54: bindingdb.org; 62: bindingdb.org; 67: bindingdb.org; 75: bindingdb.org; 84: www.bindingdb.org; 86: www.bindingdb.org
  - urls: 5: https://bindingdb.org/rest/; 6: https://bindingdb.org/axis2/services/BDBService/; 28: https://bindingdb.org/rest/getLigandsByUniprot?uniprot={UNIPROT_ID};{IC50_cutoff_nM}&response=application/json; 36: https://bindingdb.org/rest/getLigandsByUniprot?uniprot=P35355;100&response=application/json; 41: https://bindingdb.org/rest/getLigandsByUniprots?uniprot={IDs}&cutoff={nM}&response=application/json; 49: https://bindingdb.org/rest/getLigandsByUniprots?uniprot=P00176,P00183&cutoff=10000&response=application/json; 54: https://bindingdb.org/rest/getLigandsByPDBs?pdb={PDBs}&cutoff={nM}&identity={percent}&response=application/json; 62: https://bindingdb.org/rest/getLigandsByPDBs?pdb=1Q0L,3ANM&cutoff=100&identity=92&response=application/json; 67: https://bindingdb.org/axis2/services/BDBService/getTargetByCompound?smiles={SMILES}&cutoff={similarity}&response=application/json; 75: https://bindingdb.org/axis2/services/BDBService/getTargetByCompound?smiles=CCC%5BN%2B%5D%28C%29%28C%29CCn1nncc1COc1cc%28%3DO%29n%28C%29c2ccccc12&cutoff=0.85&response=application/json; 84: https://www.bindingdb.org/bind/chemsearch/marvin/Download.jsp; 86: https://www.bindingdb.org/rwd/bind/BindingDBRESTfulAPI.jsp
- [references/biogrid.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/biogrid.md):
  - hosts: 5: webservice.thebiogrid.org; 9: webservice.thebiogrid.org; 22: webservice.thebiogrid.org; 26: webservice.thebiogrid.org; 31: webservice.thebiogrid.org; 37: webservice.thebiogrid.org; 48: webservice.thebiogrid.org; 53: webservice.thebiogrid.org; 58: webservice.thebiogrid.org; 63: webservice.thebiogrid.org; 101: webservice.thebiogrid.org; 108: downloads.thebiogrid.org; 111: wiki.thebiogrid.org
  - urls: 5: https://webservice.thebiogrid.org/interactions; 9: https://webservice.thebiogrid.org/; 22: https://webservice.thebiogrid.org/interactions?accesskey={key}&format=json&searchNames=true&geneList={gene_symbol}&taxId={taxon_id; 26: https://webservice.thebiogrid.org/interactions?accesskey=YOUR_KEY&format=json&searchNames=true&geneList=TP53&taxId=9606&max=50; 31: https://webservice.thebiogrid.org/interactions?accesskey={key}&format=json&searchNames=true&geneList=BRCA1\|BRCA2&taxId=9606&max=100; 37: https://webservice.thebiogrid.org/interactions?accesskey={key}&format=json&searchNames=true&geneList=TP53&taxId=9606&evidenceList=Two-hybrid&includeEvidence=true&max=50; 48: https://webservice.thebiogrid.org/interactions/{interaction_id}?accesskey={key}&format=json; 53: https://webservice.thebiogrid.org/interactions?accesskey={key}&format=json&pubmedList=12345678; 58: https://webservice.thebiogrid.org/interactions?accesskey={key}&format=json&searchNames=true&geneList=TP53&taxId=9606&interSpeciesExcluded=false; 63: https://webservice.thebiogrid.org/interactions?accesskey={key}&format=json&searchNames=true&geneList=TP53&taxId=9606&includeInteractors=true&max=50; 101: https://webservice.thebiogrid.org/interactions?accesskey={key}&format=count&searchNames=true&geneList=TP53&taxId=9606; 108: https://downloads.thebiogrid.org/; 111: https://wiki.thebiogrid.org/doku.php/biogridrest
- [references/bls.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/bls.md):
  - hosts: 6: api.bls.gov; 9: api.bls.gov; 13: data.bls.gov; 57: api.bls.gov; 68: api.bls.gov; 118: data.bls.gov; 234: data.bls.gov; 235: download.bls.gov
  - urls: 6: https://api.bls.gov/publicAPI/v2; 9: https://api.bls.gov/publicAPI/v1; 13: https://data.bls.gov/registrationEngine/; 57: https://api.bls.gov/publicAPI/v2/timeseries/data/CUUR0000SA0?registrationkey=YOUR_KEY&startyear=2022&endyear=2024; 68: https://api.bls.gov/publicAPI/v2/timeseries/data/LNS14000000?registrationkey=YOUR_KEY; 118: https://data.bls.gov/cgi-bin/srgate; 234: https://data.bls.gov/cgi-bin/srgate; 235: https://download.bls.gov/pub/time.series/
- [references/brenda.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/brenda.md):
  - hosts: 7: www.brenda-enzymes.org; 11: www.brenda-enzymes.org; 41: 1.1.1.1; 52: www.brenda-enzymes.org; 53: email.com; 59: 1.1.1.1; 78: www.brenda-enzymes.org
  - urls: 7: https://www.brenda-enzymes.org/soap/brenda_zeep.wsdl; 11: https://www.brenda-enzymes.org/register.php; 52: https://www.brenda-enzymes.org/soap/brenda_zeep.wsdl; 78: https://www.brenda-enzymes.org/soap.php
- [references/cbioportal.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/cbioportal.md):
  - hosts: 5: www.cbioportal.org; 9: genie.cbioportal.org; 41: www.cbioportal.org; 42: www.cbioportal.org; 67: www.cbioportal.org; 83: www.cbioportal.org; 103: www.cbioportal.org; 146: www.cbioportal.org; 175: www.cbioportal.org; 193: docs.cbioportal.org; 202: www.cbioportal.org
  - urls: 5: https://www.cbioportal.org/api; 41: https://www.cbioportal.org/api/studies?projection=SUMMARY&pageSize=10; 42: https://www.cbioportal.org/api/studies/brca_tcga; 67: https://www.cbioportal.org/api/genes/TP53; 83: https://www.cbioportal.org/api/studies/brca_tcga/molecular-profiles; 103: https://www.cbioportal.org/api/molecular-profiles/brca_tcga_mutations/mutations?sampleListId=brca_tcga_all&entrezGeneId=7157&projection=DETAILED; 146: https://www.cbioportal.org/api/studies/brca_tcga/clinical-data?clinicalDataType=PATIENT&attributeId=OS_STATUS&projection=SUMMARY; 175: https://www.cbioportal.org/api/v3/api-docs/public; 193: https://docs.cbioportal.org/downloads/; 202: https://www.cbioportal.org/api/swagger-ui/index.html
- [references/census.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/census.md):
  - hosts: 8: api.census.gov; 12: api.census.gov; 27: api.census.gov; 65: api.census.gov; 70: api.census.gov; 75: api.census.gov; 97: api.census.gov; 109: api.census.gov; 120: api.census.gov; 131: api.census.gov; 142: api.census.gov; 154: api.census.gov; 250: api.census.gov
  - urls: 8: https://api.census.gov/data; 12: https://api.census.gov/data/key_signup.html; 27: https://api.census.gov/data/{year}/{dataset}?get={variables}&for={geography}&key=YOUR_KEY; 65: https://api.census.gov/data/2022/acs/acs5?get=NAME,B01001_001E&for=state:*&key=YOUR_KEY; 70: https://api.census.gov/data/2022/acs/acs5?get=NAME,B19013_001E&for=county:*&in=state:06&key=YOUR_KEY; 75: https://api.census.gov/data/2022/acs/acs5?get=NAME,B02001_001E,B02001_002E,B02001_003E&for=tract:000100&in=state:06&in=county:075&key=YOUR_KEY; 97: https://api.census.gov/data/2022/acs/acs1?get=NAME,B17001_001E,B17001_002E&for=state:*&key=YOUR_KEY; 109: https://api.census.gov/data/2022/acs/acs5/profile?get=NAME,DP02_0068PE&for=state:*&key=YOUR_KEY; 120: https://api.census.gov/data/2020/dec/dhc?get=NAME,P1_001N&for=state:*&key=YOUR_KEY; 131: https://api.census.gov/data/2010/dec/sf1?get=NAME,P001001&for=state:*&key=YOUR_KEY; 142: https://api.census.gov/data/2022/acs/acs5/variables.json; 154: https://api.census.gov/data/2022/acs/acs5/geography.json; 250: https://api.census.gov/data/{year}/acs/acs5/variables.html
- [references/chebi.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/chebi.md):
  - hosts: 4: www.ebi.ac.uk; 5: www.ebi.ac.uk; 22: www.ebi.ac.uk; 26: www.ebi.ac.uk; 32: www.ebi.ac.uk; 32: purl.obolibrary.org; 36: www.ebi.ac.uk; 36: purl.obolibrary.org; 42: www.ebi.ac.uk; 42: 252Fpurl.obolibrary.org; 48: www.ebi.ac.uk; 48: 252Fpurl.obolibrary.org; 53: www.ebi.ac.uk; 53: 252Fpurl.obolibrary.org; 58: www.ebi.ac.uk; 69: purl.obolibrary.org; 103: www.ebi.ac.uk; 107: www.ebi.ac.uk; 108: www.ebi.ac.uk
  - shell: 102: \`\`\`bash
  - urls: 4: https://www.ebi.ac.uk/ols4/api; 5: https://www.ebi.ac.uk/chebi/backend/api/public; 22: https://www.ebi.ac.uk/ols4/api/search?q={query}&ontology=chebi; 26: https://www.ebi.ac.uk/ols4/api/search?q=aspirin&ontology=chebi; 32: https://www.ebi.ac.uk/ols4/api/ontologies/chebi/terms?iri=http://purl.obolibrary.org/obo/CHEBI_{id; 36: https://www.ebi.ac.uk/ols4/api/ontologies/chebi/terms?iri=http://purl.obolibrary.org/obo/CHEBI_15365; 42: https://www.ebi.ac.uk/ols4/api/ontologies/chebi/terms/http%253A%252F%252Fpurl.obolibrary.org%252Fobo%252FCHEBI_{id; 48: https://www.ebi.ac.uk/ols4/api/ontologies/chebi/terms/http%253A%252F%252Fpurl.obolibrary.org%252Fobo%252FCHEBI_{id}/parents; 53: https://www.ebi.ac.uk/ols4/api/ontologies/chebi/terms/http%253A%252F%252Fpurl.obolibrary.org%252Fobo%252FCHEBI_{id}/children; 58: https://www.ebi.ac.uk/ols4/api/ontologies/chebi; 69: http://purl.obolibrary.org/obo/CHEBI_15365; 103: https://www.ebi.ac.uk/chebi/backend/api/public/es_search/; 107: https://www.ebi.ac.uk/chebi/backend/api/schema/; 108: https://www.ebi.ac.uk/about/news/updates-from-data-resources/chebi-2-0-launches/
- [references/chembl.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/chembl.md):
  - hosts: 5: www.ebi.ac.uk
  - urls: 5: https://www.ebi.ac.uk/chembl/api/data
- [references/clinicaltrials.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/clinicaltrials.md):
  - hosts: 1: ClinicalTrials.gov; 5: clinicaltrials.gov; 18: ClinicalTrials.gov; 20: ClinicalTrials.gov; 93: clinicaltrials.gov; 99: clinicaltrials.gov; 102: clinicaltrials.gov; 105: ClinicalTrials.gov
  - urls: 5: https://clinicaltrials.gov/api/v2/; 93: https://clinicaltrials.gov/AllAPIJSON.zip; 99: https://clinicaltrials.gov/AllPublicXML.zip; 102: https://clinicaltrials.gov/api/legacy/public-xml?format=zip
- [references/clinpgx.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/clinpgx.md):
  - hosts: 3: api.clinpgx.org; 4: api.pharmgkb.org; 5: api.clinpgx.org; 6: api.clinpgx.org
  - urls: 3: https://api.clinpgx.org/v1; 5: https://api.clinpgx.org/; 6: https://api.clinpgx.org/openapi.json
- [references/clinvar.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/clinvar.md):
  - hosts: 4: eutils.ncbi.nlm.nih.gov; 5: www.ncbi.nlm.nih.gov; 6: api.ncbi.nlm.nih.gov; 9: www.ncbi.nlm.nih.gov; 21: eutils.ncbi.nlm.nih.gov; 25: eutils.ncbi.nlm.nih.gov; 31: eutils.ncbi.nlm.nih.gov; 35: eutils.ncbi.nlm.nih.gov; 41: eutils.ncbi.nlm.nih.gov; 48: api.ncbi.nlm.nih.gov; 56: www.ncbi.nlm.nih.gov; 123: ftp.ncbi.nlm.nih.gov
  - urls: 4: https://eutils.ncbi.nlm.nih.gov/entrez/eutils; 5: https://www.ncbi.nlm.nih.gov/clinvar; 6: https://api.ncbi.nlm.nih.gov/variation/v0; 9: https://www.ncbi.nlm.nih.gov/account/; 21: https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=clinvar&term={query}&retmode=json; 25: https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=clinvar&term=BRCA1[gene]+AND+pathogenic[clinical_significance]&retmode=json&retmax=10; 31: https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=clinvar&id={id_list}&retmode=json; 35: https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=clinvar&id=37088,37087&retmode=json; 41: https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=clinvar&id={id}&rettype=vcv&is_variationid&retmode=xml; 48: https://api.ncbi.nlm.nih.gov/variation/v0/hgvs/{hgvs}/contextuals; 56: https://www.ncbi.nlm.nih.gov/clinvar/variation/{variation_id}/?redir=vcv; 123: https://ftp.ncbi.nlm.nih.gov/pub/clinvar/
- [references/cod.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/cod.md):
  - hosts: 6: www.crystallography.net; 87: www.crystallography.net; 95: www.crystallography.net
  - urls: 6: https://www.crystallography.net/cod; 87: https://www.crystallography.net/cod/{file}.cif; 95: https://www.crystallography.net/cod/archives/
- [references/cosmic.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/cosmic.md):
  - hosts: 3: cancer.sanger.ac.uk; 5: cancer.sanger.ac.uk
  - urls: 3: https://cancer.sanger.ac.uk/cosmic; 5: https://cancer.sanger.ac.uk/cosmic/help/file_download
- [references/dailymed.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/dailymed.md):
  - hosts: 5: dailymed.nlm.nih.gov; 33: dailymed.nlm.nih.gov; 36: dailymed.nlm.nih.gov; 39: dailymed.nlm.nih.gov; 42: dailymed.nlm.nih.gov
  - urls: 5: https://dailymed.nlm.nih.gov/dailymed/services/; 33: https://dailymed.nlm.nih.gov/dailymed/services/v2/spls.json?drug_name=metformin; 36: https://dailymed.nlm.nih.gov/dailymed/services/v2/drugnames.json?drug_name=ator; 39: https://dailymed.nlm.nih.gov/dailymed/services/v2/spls.json?drug_class_code={code_from_drugclasses; 42: https://dailymed.nlm.nih.gov/dailymed/services/v2/spls/{setid}.xml
- [references/database_selection_guide.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/database_selection_guide.md):
  - hosts: 84: MyVariant.info; 126: ClinicalTrials.gov
- [references/datacommons.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/datacommons.md):
  - env: 99: DATACOMMONS_API_KEY
  - hosts: 6: api.datacommons.org; 11: apikeys.datacommons.org; 35: api.datacommons.org; 46: api.datacommons.org; 61: api.datacommons.org; 66: api.datacommons.org; 87: api.datacommons.org; 98: api.datacommons.org; 159: www.census.gov; 206: docs.datacommons.org
  - shell: 96: \`\`\`bash
  - urls: 6: https://api.datacommons.org; 11: https://apikeys.datacommons.org/; 35: https://api.datacommons.org/v2/observation?key=YOUR_KEY&entity.dcids=country/USA&variable.dcids=Count_Person&date=LATEST&select=entity&select=variable&select=date&select=value; 46: https://api.datacommons.org/v2/observation?key=YOUR_KEY&entity.dcids=country/USA&variable.dcids=Count_Person&select=entity&select=variable&select=date&select=value; 61: https://api.datacommons.org/v2/node?key=YOUR_KEY&nodes=geoId/06&property=-; 66: https://api.datacommons.org/v2/node?key=YOUR_KEY&nodes=geoId/06&property=-; 87: https://api.datacommons.org/v2/resolve?key=YOUR_KEY&nodes=California&property=; 98: https://api.datacommons.org/v2/resolve; 159: https://www.census.gov/; 206: https://docs.datacommons.org/api/rest/v2/; 206: https://docs.datacommons.org/api/rest/v2/resolve.html
- [references/dbsnp.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/dbsnp.md):
  - hosts: 8: eutils.ncbi.nlm.nih.gov; 9: api.ncbi.nlm.nih.gov; 68: api.ncbi.nlm.nih.gov; 102: api.ncbi.nlm.nih.gov; 112: api.ncbi.nlm.nih.gov; 119: ftp.ncbi.nlm.nih.gov
  - urls: 8: https://eutils.ncbi.nlm.nih.gov/entrez/eutils/; 9: https://api.ncbi.nlm.nih.gov/variation/v0/; 68: https://api.ncbi.nlm.nih.gov/variation/v0/refsnp/334; 102: https://api.ncbi.nlm.nih.gov/variation/v0/spdi/NC_000011.10:5227002:T:A/rsids; 112: https://api.ncbi.nlm.nih.gov/variation/v0/hgvs/NC_000011.10:g.5227003T; 119: https://ftp.ncbi.nlm.nih.gov/snp/latest_release/JSON/
- [references/disgenet.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/disgenet.md):
  - hosts: 3: www.disgenet.com; 4: www.disgenet.com; 4: disgenet.org; 7: www.disgenet.com; 19: support.disgenet.com
  - urls: 3: https://www.disgenet.com/docs; 4: https://www.disgenet.com/Tools; 7: https://www.disgenet.com/Plans; 19: https://support.disgenet.com/support/solutions/articles/202000100283-what-are-the-gda-score-vda-score-disgenet-score-
- [references/drugbank.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/drugbank.md):
  - env: 8: DRUGBANK_API_KEY; 21: DRUGBANK_API_KEY
  - hosts: 6: docs.drugbank.com; 7: api.drugbank.com; 20: api.drugbank.com; 27: docs.drugbank.com; 27: api.drugbank.com
  - shell: 19: \`\`\`bash
  - urls: 6: https://docs.drugbank.com/discovery/v1/; 7: https://api.drugbank.com/discovery/v1; 20: https://api.drugbank.com/discovery/v1/drugs/DB00316/bonds; 27: https://docs.drugbank.com/v1/; 27: https://api.drugbank.com/v1
- [references/ecb.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/ecb.md):
  - hosts: 8: data-api.ecb.europa.eu; 26: data.ecb.europa.eu; 67: data-api.ecb.europa.eu; 73: data-api.ecb.europa.eu; 79: data-api.ecb.europa.eu; 98: data-api.ecb.europa.eu; 104: data-api.ecb.europa.eu; 118: data-api.ecb.europa.eu
  - urls: 8: https://data-api.ecb.europa.eu/service; 26: https://data.ecb.europa.eu/help/api/data; 67: https://data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A?startPeriod=2024-01-01&endPeriod=2024-12-31; 73: https://data-api.ecb.europa.eu/service/data/EXR/M.GBP+JPY.EUR.SP00.A?lastNObservations=12; 79: https://data-api.ecb.europa.eu/service/data/EXR/D..EUR.SP00.A?startPeriod=2024-06-01&endPeriod=2024-06-01; 98: https://data-api.ecb.europa.eu/service/dataflow/ECB; 104: https://data-api.ecb.europa.eu/service/dataflow/ECB/EXR; 118: https://data-api.ecb.europa.eu/service/datastructure/ECB/ECB_EXR1?references=children
- [references/emdb.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/emdb.md):
  - hosts: 5: www.ebi.ac.uk; 24: www.ebi.ac.uk; 27: www.ebi.ac.uk; 30: www.ebi.ac.uk
  - urls: 5: https://www.ebi.ac.uk/emdb/api/; 24: https://www.ebi.ac.uk/emdb/api/entry/EMD-1234; 27: https://www.ebi.ac.uk/emdb/api/search/ribosome?rows=5; 30: https://www.ebi.ac.uk/emdb/api/entry/experiment/EMD-1234
- [references/ena.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/ena.md):
  - hosts: 10: www.ebi.ac.uk; 43: www.ebi.ac.uk; 48: www.ebi.ac.uk; 71: www.ebi.ac.uk; 115: www.ebi.ac.uk; 129: www.ebi.ac.uk; 130: www.ebi.ac.uk; 131: www.ebi.ac.uk; 141: www.ebi.ac.uk; 153: www.ebi.ac.uk; 181: www.ebi.ac.uk; 193: www.ebi.ac.uk; 225: www.ebi.ac.uk; 237: www.ebi.ac.uk; 247: www.ebi.ac.uk; 256: www.ebi.ac.uk; 278: www.ebi.ac.uk; 288: europepmc.org; 293: www.ebi.ac.uk; 306: www.ebi.ac.uk; 320: www.ebi.ac.uk
  - urls: 10: https://www.ebi.ac.uk/ena/portal/api; 43: https://www.ebi.ac.uk/ena/portal/api/search?result=read_run&query=tax_id%3D9606%20AND%20library_strategy%3D%22RNA-Seq%22&fields=run_accession,experiment_accession,sample_accession,study_accession,instrument_platform,library_strategy,read_count,base_count&limit=5&format=json; 48: https://www.ebi.ac.uk/ena/portal/api/search?result=sequence&query=tax_id%3D9606%20AND%20description%3D%22*hemoglobin*%22&fields=accession,description,tax_id,scientific_name,base_count&limit=5&format=json; 71: https://www.ebi.ac.uk/ena/portal/api/count?result=read_run&query=tax_id%3D9606%20AND%20library_strategy%3D%22RNA-Seq%22; 115: https://www.ebi.ac.uk/ena/browser/api; 129: https://www.ebi.ac.uk/ena/browser/api/xml/PRJEB40665; 130: https://www.ebi.ac.uk/ena/browser/api/xml/SRR12345678; 131: https://www.ebi.ac.uk/ena/browser/api/xml/ERS1234567; 141: https://www.ebi.ac.uk/ena/browser/api/embl/AY585947; 153: https://www.ebi.ac.uk/ena/browser/api/fasta/AY585947; 181: https://www.ebi.ac.uk/ena/taxonomy/rest; 193: https://www.ebi.ac.uk/ena/taxonomy/rest/tax-id/9606; 225: https://www.ebi.ac.uk/ena/taxonomy/rest/scientific-name/Homo%20sapiens; 237: https://www.ebi.ac.uk/ena/taxonomy/rest/any-name/human; 247: https://www.ebi.ac.uk/ena/taxonomy/rest/suggest-for-submission/Homo%20sap; 256: https://www.ebi.ac.uk/ena/xref/rest; 278: https://www.ebi.ac.uk/ena/xref/rest/json/search?accession=A00145; 288: https://europepmc.org/; 293: https://www.ebi.ac.uk/ena/; 306: https://www.ebi.ac.uk/ena/cram; 320: https://www.ebi.ac.uk/ena/cram/md5/b1eba5b6e4440e22e1e02f7e0febd2da
- [references/encode.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/encode.md):
  - hosts: 5: www.encodeproject.org; 34: www.encodeproject.org; 37: www.encodeproject.org; 40: www.encodeproject.org
  - urls: 5: https://www.encodeproject.org; 34: https://www.encodeproject.org/search/?type=Experiment&assay_title=ChIP-seq&target.label=CTCF&format=json&limit=5; 37: https://www.encodeproject.org/experiments/ENCSR000AAA/?format=json; 40: https://www.encodeproject.org/search/?type=File&dataset=/experiments/ENCSR000AAA/&format=json
- [references/ensembl.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/ensembl.md):
  - hosts: 6: rest.ensembl.org; 11: rest.ensembl.org; 17: grch37.rest.ensembl.org; 49: rest.ensembl.org; 50: rest.ensembl.org; 90: rest.ensembl.org; 91: rest.ensembl.org; 92: rest.ensembl.org; 139: rest.ensembl.org; 144: rest.ensembl.org; 149: rest.ensembl.org; 154: rest.ensembl.org; 179: rest.ensembl.org; 193: rest.ensembl.org; 194: rest.ensembl.org; 209: rest.ensembl.org; 224: rest.ensembl.org; 225: rest.ensembl.org; 294: rest.ensembl.org; 336: rest.ensembl.org; 341: rest.ensembl.org; 354: rest.ensembl.org; 388: rest.ensembl.org; 409: rest.ensembl.org; 449: rest.ensembl.org; 480: rest.ensembl.org; 495: rest.ensembl.org; 508: rest.ensembl.org; 549: grch37.rest.ensembl.org
  - urls: 6: https://rest.ensembl.org; 11: https://rest.ensembl.org; 17: https://grch37.rest.ensembl.org; 49: https://rest.ensembl.org/lookup/symbol/homo_sapiens/TP53?content-type=application/json; 50: https://rest.ensembl.org/lookup/symbol/homo_sapiens/BRCA1?content-type=application/json;expand=1; 90: https://rest.ensembl.org/lookup/id/ENSG00000141510?content-type=application/json;expand=1; 91: https://rest.ensembl.org/lookup/id/ENST00000269305?content-type=application/json; 92: https://rest.ensembl.org/lookup/id/ENSP00000269305?content-type=application/json; 139: https://rest.ensembl.org/sequence/id/ENSP00000269305?content-type=application/json; 144: https://rest.ensembl.org/sequence/id/ENST00000269305?type=cds&content-type=application/json; 149: https://rest.ensembl.org/sequence/id/ENSG00000141510?type=genomic&expand_5prime=1000&expand_3prime=500&content-type=application/json; 154: https://rest.ensembl.org/sequence/id/ENSP00000269305?content-type=text/x-fasta; 179: https://rest.ensembl.org/sequence/region/homo_sapiens/17:7661779..7662000:1?content-type=application/json; 193: https://rest.ensembl.org/vep/homo_sapiens/hgvs/ENST00000269305.9:c.817C; 194: https://rest.ensembl.org/vep/homo_sapiens/hgvs/17:g.7675088C; 209: https://rest.ensembl.org/vep/homo_sapiens/region/17:7675088-7675088:1/G?CADD=1&content-type=application/json; 224: https://rest.ensembl.org/vep/homo_sapiens/id/rs28934578?CADD=1&content-type=application/json; 225: https://rest.ensembl.org/vep/homo_sapiens/id/rs699?content-type=application/json; 294: https://rest.ensembl.org/variation/homo_sapiens/rs699?content-type=application/json; 336: https://rest.ensembl.org/overlap/region/homo_sapiens/17:7660000-7690000?feature=gene&content-type=application/json; 341: https://rest.ensembl.org/overlap/region/homo_sapiens/17:7660000-7690000?feature=regulatory&content-type=application/json; 354: https://rest.ensembl.org/xrefs/id/ENSG00000141510?content-type=application/json; 388: https://rest.ensembl.org/xrefs/symbol/homo_sapiens/TP53?content-type=application/json; 409: https://rest.ensembl.org/homology/id/homo_sapiens/ENSG00000141510?type=orthologues&target_species=mus_musculus&content-type=application/json; 449: https://rest.ensembl.org/homology/symbol/homo_sapiens/TP53?type=orthologues&target_species=mus_musculus&content-type=application/json; 480: https://rest.ensembl.org/info/assembly/homo_sapiens?content-type=application/json; 495: https://rest.ensembl.org/phenotype/gene/homo_sapiens/TP53?content-type=application/json; 508: https://rest.ensembl.org/ld/homo_sapiens/pairwise/rs699/rs4762?population_name=1000GENOMES:phase_3:CEU&content-type=application/json
- [references/epa.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/epa.md):
  - hosts: 3: data.epa.gov; 4: www.epa.gov; 11: data.epa.gov; 33: aqs.epa.gov; 36: aqs.epa.gov; 42: aqs.epa.gov
  - urls: 3: https://data.epa.gov/dmapservice; 4: https://www.epa.gov/enviro/web-services; 11: https://data.epa.gov/dmapservice/tri.tri_facility/state_abbr/equals/VA/1:10/JSON; 33: https://aqs.epa.gov/data/api; 36: https://aqs.epa.gov/data/api/signup?email=YOUR_EMAIL; 42: https://aqs.epa.gov/data/api/dailyData/byState?email=YOUR_EMAIL&key=YOUR_KEY&param=44201&bdate=20240101&edate=20240131&state=06
- [references/eurostat.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/eurostat.md):
  - hosts: 8: ec.europa.eu; 13: ec.europa.eu; 50: ec.europa.eu; 55: ec.europa.eu; 60: ec.europa.eu; 65: ec.europa.eu; 74: ec.europa.eu; 85: ec.europa.eu; 98: ec.europa.eu; 111: ec.europa.eu; 120: ec.europa.eu; 132: ec.europa.eu; 214: ec.europa.eu
  - urls: 8: https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1; 13: https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0; 50: https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/nama_10_gdp/A.CP_MEUR.B1GQ.DE+FR?startPeriod=2018&endPeriod=2023; 55: https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/demo_pjan/A.NR.T.TOTAL.DE+FR+IT+ES?startPeriod=2015&endPeriod=2023; 60: https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/une_rt_m/M.SA.TOTAL.PC_ACT.T.EA20?startPeriod=2023-01&endPeriod=2024-12; 65: https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/prc_hicp_mmor/M.RCH_M.CP00.DE+FR+IT?startPeriod=2023-01&endPeriod=2024-06&format=JSON; 74: https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/nama_10_gdp/A.CP_MEUR.B1GQ.DE+FR?startPeriod=2018&endPeriod=2023&format=SDMX-CSV; 85: https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/datastructure/ESTAT/nama_10_gdp; 98: https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/codelist/ESTAT/GEO; 111: https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/dataflow/ESTAT/all?detail=allstubs; 120: https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data; 132: https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/nama_10_gdp?geo=DE&geo=FR&unit=CP_MEUR&na_item=B1GQ&freq=A&time=2020&time=2021&time=2022&lang=en; 214: https://ec.europa.eu/eurostat/databrowser/
- [references/fda.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/fda.md):
  - hosts: 5: api.fda.gov; 9: open.fda.gov
  - urls: 5: https://api.fda.gov; 9: https://open.fda.gov/apis/authentication/
- [references/federal-reserve.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/federal-reserve.md):
  - hosts: 6: api.stlouisfed.org; 11: fred.stlouisfed.org; 29: api.stlouisfed.org; 52: api.stlouisfed.org; 72: api.stlouisfed.org; 81: api.stlouisfed.org; 92: api.stlouisfed.org; 102: api.stlouisfed.org
  - urls: 6: https://api.stlouisfed.org/fred; 11: https://fred.stlouisfed.org/docs/api/api_key.html; 29: https://api.stlouisfed.org/fred/series?series_id=FEDFUNDS&api_key=YOUR_KEY&file_type=json; 52: https://api.stlouisfed.org/fred/series/observations?series_id=FEDFUNDS&api_key=YOUR_KEY&file_type=json&observation_start=2023-01-01&observation_end=2024-01-01; 72: https://api.stlouisfed.org/fred/series/search?search_text=monetary+base&api_key=YOUR_KEY&file_type=json&limit=10; 81: https://api.stlouisfed.org/fred/series/categories?series_id=FEDFUNDS&api_key=YOUR_KEY&file_type=json; 92: https://api.stlouisfed.org/fred/category?category_id=0&api_key=YOUR_KEY&file_type=json; 102: https://api.stlouisfed.org/fred/release/series?release_id=10&api_key=YOUR_KEY&file_type=json
- [references/fred.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/fred.md):
  - hosts: 8: api.stlouisfed.org; 12: fred.stlouisfed.org; 51: api.stlouisfed.org; 102: api.stlouisfed.org; 152: api.stlouisfed.org; 194: api.stlouisfed.org; 202: api.stlouisfed.org; 217: api.stlouisfed.org; 229: api.stlouisfed.org; 242: api.stlouisfed.org; 257: api.stlouisfed.org; 297: api.stlouisfed.org
  - urls: 8: https://api.stlouisfed.org/fred; 12: https://fred.stlouisfed.org/docs/api/api_key.html; 51: https://api.stlouisfed.org/fred/series/observations?series_id=GDP&api_key=YOUR_KEY&file_type=json&observation_start=2020-01-01&observation_end=2024-12-31&units=pch&frequency=q; 102: https://api.stlouisfed.org/fred/series?series_id=UNRATE&api_key=YOUR_KEY&file_type=json; 152: https://api.stlouisfed.org/fred/series/search?search_text=consumer+price+index&api_key=YOUR_KEY&file_type=json&limit=5; 194: https://api.stlouisfed.org/fred/category?category_id=0&api_key=YOUR_KEY&file_type=json; 202: https://api.stlouisfed.org/fred/category/children?category_id=0&api_key=YOUR_KEY&file_type=json; 217: https://api.stlouisfed.org/fred/category/series?category_id=125&api_key=YOUR_KEY&file_type=json; 229: https://api.stlouisfed.org/fred/releases?api_key=YOUR_KEY&file_type=json; 242: https://api.stlouisfed.org/fred/release/series?release_id=53&api_key=YOUR_KEY&file_type=json; 257: https://api.stlouisfed.org/fred/series/search/tags?series_search_text=mortgage+rate&api_key=YOUR_KEY&file_type=json; 297: https://api.stlouisfed.org/geofred/
- [references/gene-ontology.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/gene-ontology.md):
  - hosts: 4: www.ebi.ac.uk; 5: api.geneontology.org; 6: golr.geneontology.org; 16: api.geneontology.org; 20: api.geneontology.org; 24: api.geneontology.org; 30: api.geneontology.org; 34: api.geneontology.org; 40: api.geneontology.org; 44: api.geneontology.org; 50: api.geneontology.org; 54: api.geneontology.org; 59: api.geneontology.org; 68: www.ebi.ac.uk; 72: www.ebi.ac.uk; 78: www.ebi.ac.uk; 82: www.ebi.ac.uk; 87: www.ebi.ac.uk; 92: www.ebi.ac.uk; 97: www.ebi.ac.uk; 102: www.ebi.ac.uk; 107: www.ebi.ac.uk
  - urls: 4: https://www.ebi.ac.uk/QuickGO/services; 5: https://api.geneontology.org/api; 5: https://api.geneontology.org/openapi.json; 6: https://golr.geneontology.org/solr; 20: https://api.geneontology.org/api/ontology/term/{go_id; 24: https://api.geneontology.org/api/ontology/term/GO%3A0008150; 30: https://api.geneontology.org/api/bioentity/gene/{gene_id}/function; 34: https://api.geneontology.org/api/bioentity/gene/UniProtKB%3AP04637/function; 40: https://api.geneontology.org/api/bioentity/function/{go_id}/genes; 44: https://api.geneontology.org/api/bioentity/function/GO%3A0006915/genes?rows=20; 50: https://api.geneontology.org/api/search/entity/autocomplete/{query; 54: https://api.geneontology.org/api/search/entity/autocomplete/apoptosis; 59: https://api.geneontology.org/api/ontology/term/{go_id}/graph; 68: https://www.ebi.ac.uk/QuickGO/services/ontology/go/terms/{go_ids; 72: https://www.ebi.ac.uk/QuickGO/services/ontology/go/terms/GO:0008150; 78: https://www.ebi.ac.uk/QuickGO/services/annotation/search?geneProductId={uniprot_id; 82: https://www.ebi.ac.uk/QuickGO/services/annotation/search?geneProductId=P04637&limit=25; 87: https://www.ebi.ac.uk/QuickGO/services/annotation/search?goId=GO:0006915&taxonId=9606&limit=25; 92: https://www.ebi.ac.uk/QuickGO/services/annotation/search?geneProductId=P04637&goUsage=descendants&evidenceCode=ECO:0000269&limit=25; 97: https://www.ebi.ac.uk/QuickGO/services/ontology/go/terms/GO:0008150/children; 102: https://www.ebi.ac.uk/QuickGO/services/ontology/go/terms/GO:0006915/ancestors?relations=is_a,part_of; 107: https://www.ebi.ac.uk/QuickGO/services/ontology/go/search?query=apoptosis&limit=10
- [references/geo.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/geo.md):
  - hosts: 7: eutils.ncbi.nlm.nih.gov; 8: www.ncbi.nlm.nih.gov; 88: www.ncbi.nlm.nih.gov; 128: ncbi.nlm.nih.gov; 129: example.com
  - urls: 7: https://eutils.ncbi.nlm.nih.gov/entrez/eutils/; 8: https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi; 88: https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc={accession}&form={format}&view={detail
- [references/gnomad.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/gnomad.md):
  - hosts: 8: gnomad.broadinstitute.org; 19: gnomad.broadinstitute.org; 90: gnomad.broadinstitute.org
  - urls: 8: https://gnomad.broadinstitute.org/api; 19: https://gnomad.broadinstitute.org/api
- [references/gtex.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/gtex.md):
  - hosts: 8: gtexportal.org; 138: gtexportal.org
  - urls: 8: https://gtexportal.org/api/v2; 138: https://gtexportal.org/api/v2/openapi.json
- [references/gwas-catalog.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/gwas-catalog.md):
  - hosts: 5: www.ebi.ac.uk; 33: www.ebi.ac.uk; 36: www.ebi.ac.uk; 39: www.ebi.ac.uk; 46: ftp.ebi.ac.uk; 48: www.ebi.ac.uk
  - urls: 5: https://www.ebi.ac.uk/gwas/rest/api; 33: https://www.ebi.ac.uk/gwas/rest/api/studies/GCST001633; 36: https://www.ebi.ac.uk/gwas/rest/api/singleNucleotidePolymorphisms/rs7329174/associations; 39: https://www.ebi.ac.uk/gwas/rest/api/efoTraits/search/findByEfoTrait?trait=diabetes&page=0&size=5; 48: https://www.ebi.ac.uk/gwas/rest/documents/api.html
- [references/hca.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/hca.md):
  - hosts: 5: service.azul.data.humancellatlas.org; 29: service.azul.data.humancellatlas.org; 32: service.azul.data.humancellatlas.org; 38: service.azul.data.humancellatlas.org
  - urls: 5: https://service.azul.data.humancellatlas.org/; 29: https://service.azul.data.humancellatlas.org/index/projects?size=5&catalog={catalog; 32: https://service.azul.data.humancellatlas.org/index/summary?catalog={catalog; 38: https://service.azul.data.humancellatlas.org/openapi.json
- [references/hpo.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/hpo.md):
  - hosts: 3: ontology.jax.org; 20: ontology.jax.org; 25: ontology.jax.org; 26: ontology.jax.org
  - urls: 3: https://ontology.jax.org/api/hp; 20: https://ontology.jax.org/api/network/annotation/HP%3A0001250; 25: https://ontology.jax.org/api/hp/docs/; 26: https://ontology.jax.org/api/network/docs
- [references/human-protein-atlas.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/human-protein-atlas.md):
  - hosts: 5: www.proteinatlas.org; 22: www.proteinatlas.org; 25: www.proteinatlas.org; 45: www.proteinatlas.org
  - urls: 5: https://www.proteinatlas.org; 22: https://www.proteinatlas.org/ENSG00000141510.json; 25: https://www.proteinatlas.org/search/TP53; 45: https://www.proteinatlas.org/about/download
- [references/interpro.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/interpro.md):
  - hosts: 5: www.ebi.ac.uk; 21: www.ebi.ac.uk; 25: www.ebi.ac.uk; 31: www.ebi.ac.uk; 32: www.ebi.ac.uk; 33: www.ebi.ac.uk; 37: www.ebi.ac.uk; 42: www.ebi.ac.uk; 46: www.ebi.ac.uk; 52: www.ebi.ac.uk; 56: www.ebi.ac.uk; 62: www.ebi.ac.uk; 66: www.ebi.ac.uk; 72: www.ebi.ac.uk; 76: www.ebi.ac.uk; 81: www.ebi.ac.uk; 82: www.ebi.ac.uk; 83: www.ebi.ac.uk; 88: www.ebi.ac.uk; 96: www.ebi.ac.uk
  - urls: 5: https://www.ebi.ac.uk/interpro/api; 21: https://www.ebi.ac.uk/interpro/api/entry/interpro/{accession; 25: https://www.ebi.ac.uk/interpro/api/entry/interpro/IPR000504; 31: https://www.ebi.ac.uk/interpro/api/entry/pfam/{pfam_accession; 32: https://www.ebi.ac.uk/interpro/api/entry/smart/{smart_accession; 33: https://www.ebi.ac.uk/interpro/api/entry/prosite/{prosite_accession; 37: https://www.ebi.ac.uk/interpro/api/entry/pfam/PF00076; 42: https://www.ebi.ac.uk/interpro/api/entry/interpro?search={query; 46: https://www.ebi.ac.uk/interpro/api/entry/interpro?search=kinase; 52: https://www.ebi.ac.uk/interpro/api/entry/interpro/protein/uniprot/{uniprot_accession; 56: https://www.ebi.ac.uk/interpro/api/entry/interpro/protein/uniprot/P12345; 62: https://www.ebi.ac.uk/interpro/api/protein/uniprot/entry/interpro/{accession; 66: https://www.ebi.ac.uk/interpro/api/protein/uniprot/entry/interpro/IPR000504; 72: https://www.ebi.ac.uk/interpro/api/structure/pdb/entry/interpro/{accession; 76: https://www.ebi.ac.uk/interpro/api/structure/pdb/entry/interpro/IPR000504; 81: https://www.ebi.ac.uk/interpro/api/entry/interpro?type=domain; 82: https://www.ebi.ac.uk/interpro/api/entry/interpro?type=family; 83: https://www.ebi.ac.uk/interpro/api/entry/interpro?type=homologous_superfamily; 88: https://www.ebi.ac.uk/interpro/api/taxonomy/uniprot/entry/interpro/{accession; 96: https://www.ebi.ac.uk/interpro/api/entry/interpro?cursor=...&page_size=20
- [references/jaspar.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/jaspar.md):
  - hosts: 5: jaspar.elixir.no; 34: jaspar.elixir.no; 37: jaspar.elixir.no; 40: jaspar.elixir.no; 47: jaspar.elixir.no
  - urls: 5: https://jaspar.elixir.no/api/v1/; 34: https://jaspar.elixir.no/api/v1/matrix/MA0139.1/; 37: https://jaspar.elixir.no/api/v1/matrix/?tax_id=9606&collection=CORE&page_size=10; 40: https://jaspar.elixir.no/api/v1/matrix/MA0139.1/?format=meme; 47: https://jaspar.elixir.no/api/v1/docs/
- [references/kegg.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/kegg.md):
  - hosts: 5: rest.kegg.jp; 37: 1.1.1.1; 47: rest.kegg.jp; 50: rest.kegg.jp; 53: rest.kegg.jp; 56: rest.kegg.jp; 59: rest.kegg.jp; 62: rest.kegg.jp; 65: rest.kegg.jp; 68: rest.kegg.jp; 71: rest.kegg.jp; 80: www.kegg.jp
  - urls: 5: https://rest.kegg.jp; 47: https://rest.kegg.jp/list/pathway/hsa; 50: https://rest.kegg.jp/get/hsa00010; 53: https://rest.kegg.jp/find/compound/aspirin; 56: https://rest.kegg.jp/find/compound/C9H8O4/formula; 59: https://rest.kegg.jp/link/pathway/hsa:10458; 62: https://rest.kegg.jp/link/disease/hsa:672; 65: https://rest.kegg.jp/conv/pubchem/C00001; 68: https://rest.kegg.jp/get/C00001+C00002+C00003; 71: https://rest.kegg.jp/ddi/D00564+D00110; 80: https://www.kegg.jp/kegg/rest/keggapi.html
- [references/lincs-l1000.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/lincs-l1000.md):
  - env: 13: YOUR_API_KEY; 37: CLUE_API_KEY; 40: CLUE_API_KEY; 43: CLUE_API_KEY
  - hosts: 1: Clue.io; 4: clue.io; 8: api.clue.io; 12: clue.io; 36: api.clue.io; 39: api.clue.io; 42: api.clue.io; 63: clue.io; 67: clue.io
  - shell: 34: \`\`\`bash
  - urls: 8: https://api.clue.io/api; 36: https://api.clue.io/api/perts; 39: https://api.clue.io/api/genes; 42: https://api.clue.io/api/sigs; 67: https://clue.io/developer-resources
- [references/materials-project.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/materials-project.md):
  - env: 15: MP_API_KEY
  - hosts: 6: api.materialsproject.org; 11: materialsproject.org; 22: api.materialsproject.org; 118: docs.materialsproject.org
  - urls: 6: https://api.materialsproject.org; 11: https://materialsproject.org; 22: https://api.materialsproject.org/openapi.json; 118: https://docs.materialsproject.org/downloading-data/using-the-api/tips-for-large-downloads
- [references/metabolomics-workbench.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/metabolomics-workbench.md):
  - hosts: 5: www.metabolomicsworkbench.org; 74: www.metabolomicsworkbench.org; 77: www.metabolomicsworkbench.org; 80: www.metabolomicsworkbench.org; 83: www.metabolomicsworkbench.org; 86: www.metabolomicsworkbench.org; 89: www.metabolomicsworkbench.org; 92: www.metabolomicsworkbench.org; 95: www.metabolomicsworkbench.org; 104: www.metabolomicsworkbench.org
  - urls: 5: https://www.metabolomicsworkbench.org/rest/; 74: https://www.metabolomicsworkbench.org/rest/study/study_id/ST000001/summary; 77: https://www.metabolomicsworkbench.org/rest/study/study_id/ST000001/metabolites; 80: https://www.metabolomicsworkbench.org/rest/study/study_title/diabetes/summary; 83: https://www.metabolomicsworkbench.org/rest/compound/formula/C6H12O6/all; 86: https://www.metabolomicsworkbench.org/rest/compound/pubchem_cid/5793/all; 89: https://www.metabolomicsworkbench.org/rest/refmet/match/alpha-D-Glucose/name; 92: https://www.metabolomicsworkbench.org/rest/moverz/MB/635.52/M%2BH/0.5; 95: https://www.metabolomicsworkbench.org/rest/moverz/exactmass/PC(34:1)/M%2BH; 104: https://www.metabolomicsworkbench.org/tools/mw_rest.php
- [references/monarch.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/monarch.md):
  - hosts: 5: api.monarchinitiative.org; 33: api.monarchinitiative.org; 36: api.monarchinitiative.org; 39: api.monarchinitiative.org
  - urls: 5: https://api.monarchinitiative.org/v3/api; 33: https://api.monarchinitiative.org/v3/api/search?q=Marfan+syndrome&limit=5; 36: https://api.monarchinitiative.org/v3/api/entity/MONDO:0007947; 39: https://api.monarchinitiative.org/v3/api/association?entity=HGNC%3A3603&category=biolink:GeneToPhenotypicFeatureAssociation&limit=10
- [references/mousemine.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/mousemine.md):
  - hosts: 5: www.mousemine.org; 24: www.mousemine.org; 27: www.mousemine.org
  - urls: 5: https://www.mousemine.org/mousemine/service; 24: https://www.mousemine.org/mousemine/service/search?q=Brca1&format=json; 27: https://www.mousemine.org/mousemine/service/templates?format=json
- [references/myvariant.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/myvariant.md):
  - hosts: 1: MyVariant.info; 3: myvariant.info; 4: docs.myvariant.info; 5: docs.myvariant.info
  - urls: 3: https://myvariant.info/v1; 4: https://docs.myvariant.info/en/latest/doc/variant_annotation_service.html; 5: https://docs.myvariant.info/en/latest/doc/variant_query_service.html
- [references/nasa-exoplanet-archive.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/nasa-exoplanet-archive.md):
  - hosts: 6: exoplanetarchive.ipac.caltech.edu; 28: exoplanetarchive.ipac.caltech.edu; 33: exoplanetarchive.ipac.caltech.edu; 38: exoplanetarchive.ipac.caltech.edu; 43: exoplanetarchive.ipac.caltech.edu; 102: exoplanetarchive.ipac.caltech.edu
  - urls: 6: https://exoplanetarchive.ipac.caltech.edu; 28: https://exoplanetarchive.ipac.caltech.edu/TAP/sync?query=SELECT; 33: https://exoplanetarchive.ipac.caltech.edu/TAP/sync?query=SELECT; 38: https://exoplanetarchive.ipac.caltech.edu/TAP/sync?query=SELECT; 43: https://exoplanetarchive.ipac.caltech.edu/TAP/sync?query=SELECT; 102: https://exoplanetarchive.ipac.caltech.edu/cgi-bin/TblView/nph-tblView?app=ExoTbls&config=PS
- [references/nasa.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/nasa.md):
  - hosts: 6: api.nasa.gov; 12: api.nasa.gov; 22: science.nasa.gov; 23: science.nasa.gov; 24: science.nasa.gov; 36: schlotterer.notion.site; 56: api.nasa.gov; 86: api.nasa.gov
  - urls: 6: https://api.nasa.gov; 12: https://api.nasa.gov/#signUp; 22: https://science.nasa.gov/wp-json/wp/v2/apod-basic/260911; 23: https://science.nasa.gov/wp-json/wp/v2/apod-basic?page=1&per_page=5; 24: https://science.nasa.gov/wp-json/wp/v2/apod-basic?date_from=260901&date_to=260930; 36: https://schlotterer.notion.site/APOD-Feed-And-API-User-Guide-39697d8747c38015a53edfdde76d4f5e; 56: https://api.nasa.gov/neo/rest/v1/feed?start_date=2024-01-01&end_date=2024-01-03&api_key=DEMO_KEY; 86: https://api.nasa.gov/assets/html/header.html; 86: https://api.nasa.gov/assets/json/apis.json
- [references/ncbi-gene.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/ncbi-gene.md):
  - hosts: 5: eutils.ncbi.nlm.nih.gov; 10: www.ncbi.nlm.nih.gov
  - urls: 5: https://eutils.ncbi.nlm.nih.gov/entrez/eutils/; 10: https://www.ncbi.nlm.nih.gov/account/settings/
- [references/ncbi-protein.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/ncbi-protein.md):
  - hosts: 8: eutils.ncbi.nlm.nih.gov; 12: www.ncbi.nlm.nih.gov
  - urls: 8: https://eutils.ncbi.nlm.nih.gov/entrez/eutils/; 12: https://www.ncbi.nlm.nih.gov/account/
- [references/ncbi-taxonomy.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/ncbi-taxonomy.md):
  - hosts: 8: eutils.ncbi.nlm.nih.gov; 12: ncbi.nlm.nih.gov
  - urls: 8: https://eutils.ncbi.nlm.nih.gov/entrez/eutils/
- [references/nist.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/nist.md):
  - hosts: 11: physics.nist.gov; 18: physics.nist.gov; 24: physics.nist.gov; 30: physics.nist.gov; 40: physics.nist.gov; 47: physics.nist.gov; 64: physics.nist.gov; 69: physics.nist.gov; 78: webbook.nist.gov; 85: webbook.nist.gov; 90: webbook.nist.gov; 95: webbook.nist.gov; 100: webbook.nist.gov
  - urls: 11: https://physics.nist.gov/cgi-bin/cuu; 18: https://physics.nist.gov/cuu/Constants/Table/allascii.txt; 24: https://physics.nist.gov/cgi-bin/cuu/Value?{constant_key; 30: https://physics.nist.gov/cgi-bin/cuu/Value?h; 40: https://physics.nist.gov/cgi-bin/ASD; 47: https://physics.nist.gov/cgi-bin/ASD/lines1.pl?spectra={element}&low_w={min_wavelength}&upp_w={max_wavelength}&unit={unit}&format={format; 64: https://physics.nist.gov/cgi-bin/ASD/lines1.pl?spectra=H&low_w=3000&upp_w=7000&unit=0&format=2&line_out=0&show_obs_wl=1&A_out=1; 69: https://physics.nist.gov/cgi-bin/ASD/energy1.pl?spectrum={element}&units={units}&format={format; 78: https://webbook.nist.gov/cgi/cbook.cgi; 85: https://webbook.nist.gov/cgi/cbook.cgi?Name={compound}&Units=SI; 90: https://webbook.nist.gov/cgi/cbook.cgi?ID={cas_number}&Units=SI; 95: https://webbook.nist.gov/cgi/cbook.cgi?Formula={formula}&Units=SI; 100: https://webbook.nist.gov/cgi/cbook.cgi?JCAMP=C{cas_no_dashes}&Index=0&Type=IR
- [references/noaa.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/noaa.md):
  - hosts: 5: www.ncdc.noaa.gov; 9: www.ncdc.noaa.gov; 48: www.ncdc.noaa.gov; 91: www.ncdc.noaa.gov; 115: www.ncdc.noaa.gov; 145: www.ncdc.noaa.gov; 180: www.ncdc.noaa.gov; 201: www.ncei.noaa.gov
  - shell: 46: \`\`\`bash; 89: \`\`\`bash; 113: \`\`\`bash; 143: \`\`\`bash; 178: \`\`\`bash
  - urls: 5: https://www.ncdc.noaa.gov/cdo-web/api/v2; 9: https://www.ncdc.noaa.gov/cdo-web/token; 48: https://www.ncdc.noaa.gov/cdo-web/api/v2/data?datasetid=GHCND&datatypeid=TMAX&stationid=GHCND:USW00013874&startdate=2024-01-01&enddate=2024-01-31&units=metric&limit=31; 91: https://www.ncdc.noaa.gov/cdo-web/api/v2/datasets?limit=10; 115: https://www.ncdc.noaa.gov/cdo-web/api/v2/datatypes?datasetid=GHCND&limit=50; 145: https://www.ncdc.noaa.gov/cdo-web/api/v2/stations?datasetid=GHCND&locationid=ZIP:28801&limit=10; 180: https://www.ncdc.noaa.gov/cdo-web/api/v2/locations?locationcategoryid=ST&limit=52; 201: https://www.ncei.noaa.gov/cdo-web/webservices/v2
- [references/omim.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/omim.md):
  - env: 10: YOUR_API_KEY
  - hosts: 5: api.omim.org; 9: omim.org; 23: api.omim.org; 27: api.omim.org; 33: api.omim.org; 39: api.omim.org; 43: api.omim.org; 48: omim.org; 48: api.omim.org; 52: api.omim.org; 56: api.omim.org; 61: api.omim.org; 66: api.omim.org
  - urls: 5: https://api.omim.org/api; 9: https://omim.org/api; 23: https://api.omim.org/api/entry?mimNumber={mim_number}&apiKey={key}&format=json; 27: https://api.omim.org/api/entry?mimNumber=141900&apiKey=YOUR_KEY&format=json; 33: https://api.omim.org/api/entry?mimNumber=141900&include=text&include=allelicVariantList&include=geneMap&apiKey={key}&format=json; 39: https://api.omim.org/api/entry/search?search={query}&apiKey={key}&format=json; 43: https://api.omim.org/api/entry/search?search=marfan+syndrome&apiKey=YOUR_KEY&format=json&start=0&limit=10; 48: https://omim.org/help/search; 48: https://api.omim.org/api/html/index.html; 52: https://api.omim.org/api/geneMap?chromosome={chrom}&apiKey={key}&format=json; 56: https://api.omim.org/api/geneMap?chromosome=17&apiKey=YOUR_KEY&format=json&start=0&limit=10; 61: https://api.omim.org/api/geneMap/search?search={query}&apiKey={key}&format=json; 66: https://api.omim.org/api/clinicalSynopsis/search?search={query}&apiKey={key}&format=json
- [references/opentargets.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/opentargets.md):
  - hosts: 7: api.platform.opentargets.org; 14: api.platform.opentargets.org; 26: api.platform.opentargets.org; 360: platform.opentargets.org; 362: api.platform.opentargets.org; 362: platform-docs.opentargets.org
  - shell: 11: \`\`\`bash
  - urls: 7: https://api.platform.opentargets.org/api/v4/graphql; 14: https://api.platform.opentargets.org/api/v4/graphql; 26: https://api.platform.opentargets.org/api/v4/graphql; 360: https://platform.opentargets.org; 362: https://api.platform.opentargets.org/api/v4/graphql/schema; 362: https://platform-docs.opentargets.org/data-access/graphql-api
- [references/openweathermap.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/openweathermap.md):
  - hosts: 5: api.openweathermap.org; 9: home.openweathermap.org; 14: openweathermap.org; 44: api.openweathermap.org; 99: api.openweathermap.org; 150: api.openweathermap.org; 156: api.openweathermap.org; 161: api.openweathermap.org; 181: api.openweathermap.org; 186: openweathermap.org; 207: api.openweathermap.org; 247: openweathermap.org; 266: openweathermap.org
  - urls: 5: https://api.openweathermap.org; 9: https://home.openweathermap.org/users/sign_up; 14: https://openweathermap.org/price; 44: https://api.openweathermap.org/data/2.5/weather?lat=40.7128&lon=-74.0060&units=metric&appid=YOUR_KEY; 99: https://api.openweathermap.org/data/2.5/forecast?lat=51.5085&lon=-0.1257&units=metric&cnt=8&appid=YOUR_KEY; 150: https://api.openweathermap.org/geo/1.0/direct?q=London,GB&limit=5&appid=YOUR_KEY; 156: https://api.openweathermap.org/geo/1.0/reverse?lat=51.5085&lon=-0.1257&limit=1&appid=YOUR_KEY; 161: https://api.openweathermap.org/geo/1.0/zip?zip=90210,US&appid=YOUR_KEY; 181: https://api.openweathermap.org/data/3.0/onecall?lat=40.7128&lon=-74.006&exclude=minutely,alerts&units=metric&appid=YOUR_KEY; 186: https://openweathermap.org/api/one-call-4; 207: https://api.openweathermap.org/data/2.5/air_pollution?lat=40.7128&lon=-74.006&appid=YOUR_KEY; 247: https://openweathermap.org/img/wn/{icon}@2x.png; 266: https://openweathermap.org/img/wn/{icon}@2x.png
- [references/pdb.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/pdb.md):
  - hosts: 4: data.rcsb.org; 5: search.rcsb.org; 6: data.rcsb.org; 7: files.rcsb.org; 19: data.rcsb.org; 23: data.rcsb.org; 29: data.rcsb.org; 33: data.rcsb.org; 40: data.rcsb.org; 45: search.rcsb.org; 98: files.rcsb.org; 99: files.rcsb.org; 104: data.rcsb.org
  - urls: 4: https://data.rcsb.org/rest/v1; 5: https://search.rcsb.org/rcsbsearch/v2/query; 6: https://data.rcsb.org/graphql; 7: https://files.rcsb.org; 19: https://data.rcsb.org/rest/v1/core/entry/{entry_id; 23: https://data.rcsb.org/rest/v1/core/entry/4HHB; 29: https://data.rcsb.org/rest/v1/core/polymer_entity/{entry_id}/{entity_id; 33: https://data.rcsb.org/rest/v1/core/polymer_entity/4HHB/1; 40: https://data.rcsb.org/rest/v1/core/assembly/{entry_id}/{assembly_id; 45: https://search.rcsb.org/rcsbsearch/v2/query; 98: https://files.rcsb.org/download/{entry_id}.cif; 99: https://files.rcsb.org/download/{entry_id}.pdb; 104: https://data.rcsb.org/graphql
- [references/pride.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/pride.md):
  - hosts: 3: www.ebi.ac.uk; 4: www.ebi.ac.uk
  - urls: 3: https://www.ebi.ac.uk/pride/ws/archive/v3; 4: https://www.ebi.ac.uk/pride/ws/archive/v3/v3/api-docs
- [references/pubchem.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/pubchem.md):
  - hosts: 6: pubchem.ncbi.nlm.nih.gov; 150: pubchem.ncbi.nlm.nih.gov
  - urls: 6: https://pubchem.ncbi.nlm.nih.gov/rest/pug; 150: https://pubchem.ncbi.nlm.nih.gov/docs/pug-rest
- [references/quickgo.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/quickgo.md):
  - hosts: 5: www.ebi.ac.uk; 33: www.ebi.ac.uk; 36: www.ebi.ac.uk; 39: www.ebi.ac.uk
  - urls: 5: https://www.ebi.ac.uk/QuickGO/services/; 33: https://www.ebi.ac.uk/QuickGO/services/ontology/go/terms/GO:0003723; 36: https://www.ebi.ac.uk/QuickGO/services/annotation/search?goId=GO:0003723&taxonId=9606&limit=10; 39: https://www.ebi.ac.uk/QuickGO/services/ontology/go/search?query=apoptosis&limit=5
- [references/reactome.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/reactome.md):
  - hosts: 6: reactome.org
  - urls: 6: https://reactome.org/ContentService
- [references/regulomedb.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/regulomedb.md):
  - hosts: 8: regulomedb.org; 9: regulomedb.org
  - urls: 8: https://regulomedb.org/regulome-search/; 9: https://regulomedb.org/regulome-help/
- [references/retrieval-contract.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/retrieval-contract.md):
  - hosts: 31: ClinicalTrials.gov
- [references/rummageo.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/rummageo.md):
  - hosts: 3: rummageo.com; 4: github.com; 5: github.com; 11: rummageo.com
  - shell: 10: \`\`\`bash
  - urls: 3: https://rummageo.com/graphql; 4: https://github.com/MaayanLab/rummageo/blob/rummageo/src/graphql/core.graphql; 5: https://github.com/MaayanLab/rummageo/blob/rummageo/src/lib/postgraphile.ts; 11: https://rummageo.com/graphql
- [references/sdss.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/sdss.md):
  - hosts: 6: skyserver.sdss.org; 30: skyserver.sdss.org; 64: skyserver.sdss.org; 110: skyserver.sdss.org; 117: data.sdss.org; 132: skyserver.sdss.org
  - urls: 6: https://skyserver.sdss.org/dr18/SkyServerWS; 30: https://skyserver.sdss.org/dr18/SkyServerWS/SearchTools/SqlSearch?cmd=SELECT; 64: https://skyserver.sdss.org/dr18/SkyServerWS/SearchTools/RadialSearch?ra=180&dec=0.5&radius=2&whichway=equatorial&whichquery=imaging&format=json&limit=10; 110: https://skyserver.sdss.org/dr18/SkyServerWS/ImgCutout/getjpeg?ra=180.0&dec=0.5&scale=0.4&width=256&height=256; 117: https://data.sdss.org/sas/dr18/; 132: https://skyserver.sdss.org/CasJobs/
- [references/sec-edgar.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/sec-edgar.md):
  - hosts: 7: data.sec.gov; 8: www.sec.gov; 9: data.sec.gov; 15: mycompany.com; 30: www.sec.gov; 30: efts.sec.gov; 30: data.sec.gov; 34: www.sec.gov; 51: www.sec.gov; 54: www.sec.gov; 66: www.sec.gov; 73: data.sec.gov; 78: data.sec.gov; 113: data.sec.gov; 125: data.sec.gov; 158: data.sec.gov; 163: data.sec.gov; 166: facts.us; 188: data.sec.gov; 206: data.sec.gov; 229: www.sec.gov; 234: www.sec.gov; 257: data.sec.gov; 259: www.sec.gov
  - urls: 7: https://data.sec.gov; 8: https://www.sec.gov; 9: https://data.sec.gov/api/xbrl; 30: https://www.sec.gov/edgar/search/; 34: https://www.sec.gov/cgi-bin/browse-edgar; 51: https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=AAPL&type=10-K&dateb=&owner=include&count=10&output=atom; 54: https://www.sec.gov/files/company_tickers.json; 66: https://www.sec.gov/files/company_tickers_exchange.json; 73: https://data.sec.gov/submissions/CIK{cik_padded}.json; 78: https://data.sec.gov/submissions/CIK0000320193.json; 113: https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/{taxonomy}/{tag}.json; 125: https://data.sec.gov/api/xbrl/companyconcept/CIK0000320193/us-gaap/RevenueFromContractWithCustomerExcludingAssessedTax.json; 158: https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json; 163: https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json; 188: https://data.sec.gov/api/xbrl/frames/{taxonomy}/{tag}/{unit}/{period}.json; 206: https://data.sec.gov/api/xbrl/frames/us-gaap/Assets/USD/CY2023Q4I.json; 229: https://www.sec.gov/Archives/edgar/data/{cik}/{accession_number_no_dashes}/{filename; 234: https://www.sec.gov/Archives/edgar/data/320193/000032019324000123/aapl-20240928.htm; 259: https://www.sec.gov/Archives/edgar/full-index/
- [references/simbad.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/simbad.md):
  - hosts: 9: simbad.cds.unistra.fr; 14: simbad.cds.unistra.fr; 19: simbad.cds.unistra.fr; 20: simbad.cds.unistra.fr; 53: simbad.cds.unistra.fr; 58: simbad.cds.unistra.fr; 64: simbad.cds.unistra.fr
  - urls: 9: https://simbad.cds.unistra.fr/simbad/sim-tap/sync; 14: https://simbad.cds.unistra.fr/simbad/sim-script; 19: https://simbad.cds.unistra.fr/simbad/sim-id; 20: https://simbad.cds.unistra.fr/simbad/sim-coo; 53: https://simbad.cds.unistra.fr/simbad/sim-tap/sync?request=doQuery&lang=adql&format=json&query=SELECT; 58: https://simbad.cds.unistra.fr/simbad/sim-tap/sync?request=doQuery&lang=adql&format=json&query=SELECT; 64: https://simbad.cds.unistra.fr/simbad/sim-tap/sync?request=doQuery&lang=adql&format=json&query=SELECT
- [references/sra.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/sra.md):
  - hosts: 8: eutils.ncbi.nlm.nih.gov
  - urls: 8: https://eutils.ncbi.nlm.nih.gov/entrez/eutils/
- [references/string.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/string.md):
  - hosts: 6: string-db.org; 39: string-db.org; 73: string-db.org; 117: string-db.org; 135: string-db.org; 155: string-db.org; 190: string-db.org; 224: string-db.org; 237: string-db.org; 285: string-db.org
  - urls: 6: https://string-db.org/api; 39: https://string-db.org/api/json/get_string_ids?identifiers=TP53&species=9606; 73: https://string-db.org/api/json/interaction_partners?identifiers=TP53&species=9606&limit=10&required_score=900; 117: https://string-db.org/api/json/network?identifiers=TP53%0dBRCA1%0dATM%0dCHEK2%0dMDM2&species=9606&required_score=700; 135: https://string-db.org/api/image/network?identifiers=TP53%0dBRCA1%0dMDM2&species=9606; 155: https://string-db.org/api/json/enrichment?identifiers=TP53%0dBRCA1%0dATM%0dCHEK2%0dCDK2%0dCDKN1A&species=9606; 190: https://string-db.org/api/json/get_string_ids?identifiers=CDK2%0dp53&species=9606; 224: https://string-db.org/api/json/homology_best?identifiers=TP53&species=9606&species_b=10090; 237: https://string-db.org/api/json/ppi_enrichment?identifiers=TP53%0dBRCA1%0dATM%0dCHEK2&species=9606; 285: https://string-db.org/help/api/
- [references/tcga-gdc.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/tcga-gdc.md):
  - hosts: 5: api.gdc.cancer.gov; 43: api.gdc.cancer.gov; 46: api.gdc.cancer.gov; 51: api.gdc.cancer.gov
  - urls: 5: https://api.gdc.cancer.gov; 43: https://api.gdc.cancer.gov/projects?size=5&fields=project_id,name,primary_site; 46: https://api.gdc.cancer.gov/ssms; 51: https://api.gdc.cancer.gov/cases?filters=%7B%22op%22%3A%22in%22%2C%22content%22%3A%7B%22field%22%3A%22project.project_id%22%2C%22value%22%3A%5B%22TCGA-LUAD%22%5D%7D%7D&size=3&fields=submitter_id,disease_type
- [references/treasury.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/treasury.md):
  - hosts: 8: api.fiscaldata.treasury.gov; 51: home.treasury.gov; 57: api.fiscaldata.treasury.gov; 105: api.fiscaldata.treasury.gov; 119: api.fiscaldata.treasury.gov; 133: api.fiscaldata.treasury.gov; 145: api.fiscaldata.treasury.gov; 157: api.fiscaldata.treasury.gov; 171: api.fiscaldata.treasury.gov; 208: fiscaldata.treasury.gov
  - urls: 8: https://api.fiscaldata.treasury.gov/services/api/fiscal_service; 51: https://home.treasury.gov/treasury-daily-interest-rate-xml-feed; 57: https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v2/accounting/od/avg_interest_rates?filter=record_date:gte:2024-01-01&sort=-record_date&page[size]=100; 105: https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v2/accounting/od/debt_to_penny?filter=record_date:gte:2024-01-01&sort=-record_date&page[size]=10; 119: https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/auctions_query?filter=security_type:eq:Bill&sort=-auction_date&page[size]=10; 133: https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/mts/mts_table_5?filter=record_date:gte:2024-01-01&sort=-record_date&page[size]=50; 145: https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/mts/mts_table_9?filter=record_date:gte:2024-01-01&sort=-record_date; 157: https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/rates_of_exchange?filter=record_date:eq:2024-09-30&page[size]=200; 171: https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v2/accounting/od/interest_expense?filter=record_fiscal_year:eq:2024&sort=-record_date; 208: https://fiscaldata.treasury.gov/api-documentation/
- [references/ucsc-genome.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/ucsc-genome.md):
  - hosts: 8: api.genome.ucsc.edu; 75: api.genome.ucsc.edu; 80: api.genome.ucsc.edu; 125: genome-mysql.soe.ucsc.edu
  - urls: 8: https://api.genome.ucsc.edu; 75: https://api.genome.ucsc.edu/getData/track?genome=hg38&track=ncbiRefSeq&chrom=chr17&start=43044295&end=43125483; 80: https://api.genome.ucsc.edu/getData/sequence?genome=hg38&chrom=chr7&start=117119148&end=117119178
- [references/uniprot.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/uniprot.md):
  - hosts: 6: rest.uniprot.org; 40: rest.uniprot.org; 45: rest.uniprot.org; 50: rest.uniprot.org; 50: 2.7.11.1; 55: rest.uniprot.org; 114: rest.uniprot.org; 115: rest.uniprot.org; 125: rest.uniprot.org; 130: rest.uniprot.org; 235: rest.uniprot.org; 258: 2.7.11.1; 284: rest.uniprot.org; 291: rest.uniprot.org
  - urls: 6: https://rest.uniprot.org; 40: https://rest.uniprot.org/uniprotkb/search?query=(gene:TP53; 45: https://rest.uniprot.org/uniprotkb/search?query=(protein_name:insulin; 50: https://rest.uniprot.org/uniprotkb/search?query=(ec:2.7.11.1; 55: https://rest.uniprot.org/uniprotkb/search?query=(go:0006915; 114: https://rest.uniprot.org/uniprotkb/P04637?format=json; 115: https://rest.uniprot.org/uniprotkb/P04637.fasta; 125: https://rest.uniprot.org/uniprotkb/P04637.fasta; 130: https://rest.uniprot.org/uniprotkb/search?query=(gene:BRCA1; 235: https://rest.uniprot.org/proteomes/UP000005640?format=json; 284: https://rest.uniprot.org/; 291: https://rest.uniprot.org/configure/idmapping/fields
- [references/usgs.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/usgs.md):
  - hosts: 9: api.waterdata.usgs.gov; 11: waterservices.usgs.gov; 15: earthquake.usgs.gov; 58: earthquake.usgs.gov; 67: earthquake.usgs.gov; 82: earthquake.usgs.gov; 83: earthquake.usgs.gov; 121: earthquake.usgs.gov; 127: earthquake.usgs.gov; 128: earthquake.usgs.gov; 129: earthquake.usgs.gov; 130: earthquake.usgs.gov; 140: waterservices.usgs.gov; 177: waterservices.usgs.gov; 227: waterservices.usgs.gov; 238: waterservices.usgs.gov; 249: waterservices.usgs.gov
  - urls: 9: https://api.waterdata.usgs.gov; 11: https://waterservices.usgs.gov/; 15: https://earthquake.usgs.gov/fdsnws/event/1; 58: https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson&starttime=2024-01-01&endtime=2024-12-31&minmagnitude=5.0&minlatitude=30&maxlatitude=45&minlongitude=-125&maxlongitude=-110&orderby=magnitude; 67: https://earthquake.usgs.gov/fdsnws/event/1/query?; 82: https://earthquake.usgs.gov/earthquakes/eventpage/ci00000001; 83: https://earthquake.usgs.gov/fdsnws/event/1/query?eventid=ci00000001&format=geojson; 121: https://earthquake.usgs.gov/fdsnws/event/1/count?starttime=2024-01-01&endtime=2024-12-31&minmagnitude=4.5; 127: https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/significant_month.geojson; 128: https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_week.geojson; 129: https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_day.geojson; 130: https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_hour.geojson; 140: https://waterservices.usgs.gov/nwis; 177: https://waterservices.usgs.gov/nwis/iv/?format=json&sites=01646500&parameterCd=00060&period=P1D; 227: https://waterservices.usgs.gov/nwis/dv/?format=json&sites=01646500&parameterCd=00060&statCd=00003&startDT=2023-01-01&endDT=2023-12-31; 238: https://waterservices.usgs.gov/nwis/site/?format=rdb&stateCd=VA&siteType=ST&siteStatus=active&hasDataTypeCd=iv; 249: https://waterservices.usgs.gov/nwis/stat/?format=rdb&sites=01646500&parameterCd=00060&statReportType=daily&statTypeCd=mean,p05,p25,p50,p75,p95
- [references/uspto.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/uspto.md):
  - env: 38: USPTO_ODP_API_KEY
  - hosts: 6: search.patentsview.org; 9: search.patentsview.org; 10: patentsview.org; 11: api.patentsview.org; 18: data.uspto.gov; 19: www.uspto.gov; 20: data.uspto.gov; 24: data.uspto.gov; 25: data.uspto.gov; 26: data.uspto.gov; 27: data.uspto.gov; 28: data.uspto.gov; 29: data.uspto.gov; 36: USPTO.gov; 37: data.uspto.gov; 49: api.patentsview.org; 51: search.patentsview.org; 57: data.uspto.gov; 58: data.uspto.gov; 59: api.uspto.gov; 62: ped.uspto.gov; 69: tsdr.uspto.gov; 70: tsdrapi.uspto.gov
  - urls: 6: https://search.patentsview.org/api/v1/; 18: https://data.uspto.gov/support/transition-guide/patentsview; 19: https://www.uspto.gov/ip-policy/economic-research/patentsview; 20: https://data.uspto.gov/; 24: https://data.uspto.gov/bulkdata/datasets/pvgpatdis; 25: https://data.uspto.gov/bulkdata/datasets/pvgpattxt; 26: https://data.uspto.gov/bulkdata/datasets/pvpgpubdis; 27: https://data.uspto.gov/bulkdata/datasets/pvpgpubtxt; 28: https://data.uspto.gov/bulkdata/datasets/pvsorted; 29: https://data.uspto.gov/bulkdata/datasets/pvannual; 37: https://data.uspto.gov/apikey; 51: https://search.patentsview.org/api/v1/; 57: https://data.uspto.gov/support/transition-guide/peds; 58: https://data.uspto.gov/apis/patent-file-wrapper/search; 59: https://api.uspto.gov/api/v1/patent/applications/search; 69: https://tsdr.uspto.gov/faqview; 70: https://tsdrapi.uspto.gov
- [references/who.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/who.md):
  - hosts: 8: ghoapi.azureedge.net; 33: ghoapi.azureedge.net; 68: ghoapi.azureedge.net; 110: ghoapi.azureedge.net; 115: ghoapi.azureedge.net; 122: ghoapi.azureedge.net; 127: ghoapi.azureedge.net; 134: ghoapi.azureedge.net; 143: ghoapi.azureedge.net; 148: ghoapi.azureedge.net; 154: ghoapi.azureedge.net; 160: ghoapi.azureedge.net; 171: ghoapi.azureedge.net; 176: ghoapi.azureedge.net; 181: ghoapi.azureedge.net; 259: ghoapi.azureedge.net; 283: www.who.int
  - urls: 8: https://ghoapi.azureedge.net/api; 33: https://ghoapi.azureedge.net/api/Indicator; 68: https://ghoapi.azureedge.net/api/WHOSIS_000001; 110: https://ghoapi.azureedge.net/api/WHOSIS_000001?$filter=SpatialDim; 115: https://ghoapi.azureedge.net/api/WHOSIS_000001?$filter=SpatialDim; 122: https://ghoapi.azureedge.net/api/WHOSIS_000001?$filter=TimeDim; 127: https://ghoapi.azureedge.net/api/WHOSIS_000001?$filter=SpatialDim; 134: https://ghoapi.azureedge.net/api/WHOSIS_000001?$filter=SpatialDim; 143: https://ghoapi.azureedge.net/api/WHOSIS_000001?$top=10; 148: https://ghoapi.azureedge.net/api/WHOSIS_000001?$top=50&$skip=100; 154: https://ghoapi.azureedge.net/api/WHOSIS_000001?$filter=SpatialDim; 160: https://ghoapi.azureedge.net/api/WHOSIS_000001?$filter=SpatialDim; 171: https://ghoapi.azureedge.net/api/DIMENSION/COUNTRY/DimensionValues; 176: https://ghoapi.azureedge.net/api/DIMENSION/REGION/DimensionValues; 181: https://ghoapi.azureedge.net/api/DIMENSION/SEX/DimensionValues; 259: https://ghoapi.azureedge.net/api/$metadata#; 283: https://www.who.int/data/gho
- [references/worldbank.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/worldbank.md):
  - hosts: 6: api.worldbank.org; 32: api.worldbank.org; 37: api.worldbank.org; 46: api.worldbank.org; 55: api.worldbank.org; 66: api.worldbank.org; 75: api.worldbank.org; 84: api.worldbank.org; 93: api.worldbank.org; 104: api.worldbank.org; 109: api.worldbank.org; 118: api.worldbank.org; 127: api.worldbank.org
  - urls: 6: https://api.worldbank.org/v2; 32: https://api.worldbank.org/v2/country/US/indicator/NY.GDP.MKTP.CD?format=json&date=2015:2023; 37: https://api.worldbank.org/v2/country/US/indicator/NY.GDP.MKTP.CD?format=json&MRV=5; 46: https://api.worldbank.org/v2/country/US;GB;CN;IN/indicator/SP.POP.TOTL?format=json&date=2020:2023; 55: https://api.worldbank.org/v2/country/all/indicator/SI.POV.DDAY?format=json&date=2020&per_page=300; 66: https://api.worldbank.org/v2/country/WLD/indicator/NY.GDP.MKTP.CD?format=json&date=2020:2023; 75: https://api.worldbank.org/v2/country?format=json&per_page=300; 84: https://api.worldbank.org/v2/country/US?format=json; 93: https://api.worldbank.org/v2/indicator?format=json&per_page=100; 104: https://api.worldbank.org/v2/topic/3/indicator?format=json; 109: https://api.worldbank.org/v2/source/2/indicator?format=json&per_page=50; 118: https://api.worldbank.org/v2/topic?format=json; 127: https://api.worldbank.org/v2/source?format=json
- [references/zinc.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/database-lookup/references/zinc.md):
  - hosts: 6: zinc.docking.org
  - urls: 6: https://zinc.docking.org

### datamol

- [SKILL.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/datamol/SKILL.md):
  - hosts: 213: docs.datamol.io; 214: www.rdkit.org; 215: github.com; 225: doi.org; 227: arxiv.org; 229: arxiv.org; 230: export.arxiv.org
  - install: 45: uv pip install
  - shell: 44: \`\`\`bash
  - urls: 132: s3://bucket/compounds.sdf; 213: https://docs.datamol.io/; 214: https://www.rdkit.org/docs/; 215: https://github.com/datamol-io/datamol; 225: https://doi.org/10.48550/arXiv.2609.00065; 227: https://arxiv.org/abs/2609.00065; 229: https://arxiv.org/abs/2609.00065; 230: http://export.arxiv.org/api/query?id_list=2609.00065
- [references/conformers_module.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/datamol/references/conformers_module.md):
  - hosts: 3: docs.datamol.io
  - urls: 3: https://docs.datamol.io/stable/api/datamol.conformers.html
- [references/core_api.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/datamol/references/core_api.md):
  - hosts: 3: docs.datamol.io
  - urls: 3: https://docs.datamol.io/stable/api/datamol.mol.html
- [references/core_workflows.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/datamol/references/core_workflows.md): no matches
- [references/descriptors_viz.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/datamol/references/descriptors_viz.md):
  - hosts: 3: docs.datamol.io; 4: docs.datamol.io
  - urls: 3: https://docs.datamol.io/stable/api/datamol.descriptors.html; 4: https://docs.datamol.io/stable/api/datamol.viz.html
- [references/fragments_scaffolds.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/datamol/references/fragments_scaffolds.md):
  - hosts: 3: docs.datamol.io; 4: docs.datamol.io
  - urls: 3: https://docs.datamol.io/stable/api/datamol.fragment.html; 4: https://docs.datamol.io/stable/api/datamol.scaffold.html
- [references/io_module.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/datamol/references/io_module.md):
  - hosts: 3: docs.datamol.io; 3: datamol.io
  - urls: 3: https://docs.datamol.io/stable/api/datamol.io.html; 70: s3://bucket/compounds.sdf; 71: gs://bucket/results.sdf
- [references/reactions_data.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/datamol/references/reactions_data.md):
  - hosts: 3: docs.datamol.io; 4: docs.datamol.io
  - urls: 3: https://docs.datamol.io/stable/api/datamol.reactions.html; 4: https://docs.datamol.io/stable/api/datamol.data.html
- [references/review.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/datamol/references/review.md):
  - hosts: 9: pypi.org; 11: github.com; 12: docs.datamol.io; 14: github.com; 17: docs.datamol.io; 18: docs.datamol.io; 19: docs.datamol.io; 20: docs.datamol.io; 21: docs.datamol.io; 22: docs.datamol.io; 22: datamol.io; 23: docs.datamol.io; 24: docs.datamol.io; 25: docs.datamol.io; 26: docs.datamol.io; 27: docs.datamol.io; 28: docs.datamol.io; 29: docs.datamol.io
  - urls: 9: https://pypi.org/project/datamol/0.13.0/; 11: https://github.com/datamol-io/datamol/releases/tag/0.13.0; 12: https://docs.datamol.io/stable/migration.html; 14: https://github.com/datamol-io/datamol/tree/0.13.0/datamol; 17: https://docs.datamol.io/stable/api/datamol.mol.html; 18: https://docs.datamol.io/stable/api/datamol.convert.html; 19: https://docs.datamol.io/stable/api/datamol.fp.html; 20: https://docs.datamol.io/stable/api/datamol.similarity.html; 21: https://docs.datamol.io/stable/api/datamol.cluster.html; 22: https://docs.datamol.io/stable/api/datamol.io.html; 23: https://docs.datamol.io/stable/api/datamol.descriptors.html; 24: https://docs.datamol.io/stable/api/datamol.viz.html; 25: https://docs.datamol.io/stable/api/datamol.conformers.html; 26: https://docs.datamol.io/stable/api/datamol.scaffold.html; 27: https://docs.datamol.io/stable/api/datamol.fragment.html; 28: https://docs.datamol.io/stable/api/datamol.reactions.html; 29: https://docs.datamol.io/stable/api/datamol.data.html
- [references/workflow_patterns.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/datamol/references/workflow_patterns.md): no matches

### deepchem

- [SKILL.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/deepchem/SKILL.md):
  - hosts: 89: deepchem.readthedocs.io; 90: deepchem.readthedocs.io; 154: doi.org; 156: arxiv.org; 158: arxiv.org; 159: export.arxiv.org
  - install: 74: uv pip install
  - shell: 72: \`\`\`bash; 113: \`\`\`bash
  - urls: 89: https://deepchem.readthedocs.io/en/2.8.0/get_started/installation.html; 90: https://deepchem.readthedocs.io/en/2.8.0/get_started/requirements.html; 154: https://doi.org/10.48550/arXiv.2609.00065; 156: https://arxiv.org/abs/2609.00065; 158: https://arxiv.org/abs/2609.00065; 159: http://export.arxiv.org/api/query?id_list=2609.00065
- [references/api_reference.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/deepchem/references/api_reference.md):
  - hosts: 127: pypi.org; 128: deepchem.readthedocs.io; 129: deepchem.readthedocs.io; 130: deepchem.readthedocs.io; 131: deepchem.readthedocs.io; 132: github.com; 133: github.com; 134: github.com
  - urls: 127: https://pypi.org/project/deepchem/2.8.0/; 128: https://deepchem.readthedocs.io/en/2.8.0/api_reference/featurizers.html; 129: https://deepchem.readthedocs.io/en/2.8.0/api_reference/models.html; 130: https://deepchem.readthedocs.io/en/2.8.0/api_reference/splitters.html; 131: https://deepchem.readthedocs.io/en/2.8.0/api_reference/moleculenet.html; 132: https://github.com/deepchem/deepchem/blob/2.8.0/deepchem/molnet/load_function/molnet_loader.py; 133: https://github.com/deepchem/deepchem/blob/2.8.0/deepchem/models/torch_models/hf_models.py; 134: https://github.com/deepchem/deepchem/blob/2.8.0/deepchem/hyper/grid_search.py
- [references/core_capabilities.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/deepchem/references/core_capabilities.md): no matches
- [references/review.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/deepchem/references/review.md):
  - hosts: 69: www.dgl.ai; 79: pypi.org; 81: github.com; 82: github.com; 83: github.com; 84: huggingface.co; 85: huggingface.co; 86: huggingface.co; 87: huggingface.co
  - urls: 69: https://www.dgl.ai/pages/start.html; 79: https://pypi.org/project/deepchem/2.8.0/; 81: https://github.com/deepchem/deepchem/blob/2.8.0/deepchem/models/__init__.py; 82: https://github.com/deepchem/deepchem/blob/2.8.0/deepchem/models/torch_models/hf_models.py; 83: https://github.com/deepchem/deepchem/blob/2.8.0/deepchem/models/torch_models/grover.py; 84: https://huggingface.co/ibm-research/MoLFormer-XL-both-10pct; 85: https://huggingface.co/ibm-research/MoLFormer-XL-both-10pct/blob/main/config.json; 86: https://huggingface.co/seyonec/ChemBERTa-zinc-base-v1; 87: https://huggingface.co/Rostlab/prot_bert
- [references/typical_workflows.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/deepchem/references/typical_workflows.md):
  - shell: 9: \`\`\`bash; 22: \`\`\`bash; 36: \`\`\`bash
- [references/workflows.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/deepchem/references/workflows.md):
  - hosts: 60: huggingface.co; 62: huggingface.co; 71: huggingface.co; 77: github.com; 93: github.com; 105: deepchem.readthedocs.io; 116: huggingface.co; 137: github.com
  - remote_code_reference: 66: trust_remote_code=True
  - urls: 60: https://huggingface.co/seyonec/ChemBERTa-zinc-base-v1; 62: https://huggingface.co/ibm-research/MoLFormer-XL-both-10pct; 71: https://huggingface.co/docs/transformers/models; 77: https://github.com/deepchem/deepchem/blob/2.8.0/deepchem/models/torch_models/grover.py; 93: https://github.com/deepchem/deepchem/blob/2.8.0/deepchem/models/torch_models/molgan.py; 105: https://deepchem.readthedocs.io/en/2.8.0/api_reference/featurizers.html#cgcnnfeaturizer; 116: https://huggingface.co/Rostlab/prot_bert; 137: https://github.com/deepchem/deepchem/blob/2.8.0/deepchem/models/torch_models/torch_model.py
- [scripts/_common.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/deepchem/scripts/_common.py): no matches
- [scripts/graph_neural_network.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/deepchem/scripts/graph_neural_network.py): no matches
- [scripts/predict_solubility.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/deepchem/scripts/predict_solubility.py): no matches
- [scripts/transfer_learning.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/deepchem/scripts/transfer_learning.py): no matches

### depmap

- [SKILL.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/depmap/SKILL.md):
  - hosts: 27: depmap.org; 34: depmap.org; 41: forum.depmap.org; 43: depmap.org; 110: github.com; 111: forum.depmap.org; 199: forum.depmap.org; 221: forum.depmap.org; 222: forum.depmap.org; 223: github.com; 224: doi.org; 225: depmap.org
  - urls: 27: https://depmap.org/portal/data_page/; 34: https://depmap.org/portal/api/no-captcha/download/files; 41: https://forum.depmap.org/t/provide-an-open-endpoint-for-latest-version-retrieval/4652; 43: https://depmap.org/portal/api/download/files; 110: https://github.com/broadinstitute/depmap-portal/blob/master/frontend/packages/portal-frontend/src/dataPage/components/MapSection.tsx; 111: https://forum.depmap.org/t/depmap-metadata/3694; 199: https://forum.depmap.org/t/crispr-co-depency-top-hits-obscured-by-newly-added-screens/4503; 221: https://forum.depmap.org/t/announcing-the-26q1-release/4606; 222: https://forum.depmap.org/t/announcing-the-25q2-release/4257; 223: https://github.com/broadinstitute/chronos; 224: https://doi.org/10.1186/s13059-021-02540-7; 225: https://depmap.org/repurposing/
- [references/dependency_analysis.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/depmap/references/dependency_analysis.md):
  - hosts: 10: depmap.org; 14: depmap.org; 18: forum.depmap.org; 32: forum.depmap.org; 33: github.com; 65: github.com; 66: forum.depmap.org; 73: forum.depmap.org; 97: forum.depmap.org; 98: forum.depmap.org; 111: forum.depmap.org; 117: depmap.org; 161: ndownloader.figshare.com; 162: ndownloader.figshare.com
  - urls: 10: https://depmap.org/portal/api/no-captcha/download/files; 14: https://depmap.org/portal/data_page/; 18: https://forum.depmap.org/t/provide-an-open-endpoint-for-latest-version-retrieval/4652; 32: https://forum.depmap.org/t/meaning-of-efficacy-column-in-crisprinferredguideefficacy-csv-a-few-other-questions/3473; 33: https://github.com/broadinstitute/chronos; 65: https://github.com/broadinstitute/depmap-portal/blob/master/frontend/packages/portal-frontend/src/dataPage/components/MapSection.tsx; 66: https://forum.depmap.org/t/multiple-omics-expression-profiles/4585; 73: https://forum.depmap.org/t/how-should-crisprinferredmodelefficacy-csv-identifiers-be-mapped-in-depmap-public-26q1/4653; 97: https://forum.depmap.org/t/announcing-the-25q2-release/4257; 98: https://forum.depmap.org/t/26q1-omicscngenewgs-csv-normalization/4656; 111: https://forum.depmap.org/t/crispr-co-depency-top-hits-obscured-by-newly-added-screens/4503; 117: https://depmap.org/repurposing/; 161: https://ndownloader.figshare.com/files/20237700; 162: https://ndownloader.figshare.com/files/20238123
- [scripts/depmap_data.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/depmap/scripts/depmap_data.py):
  - hosts: 19: depmap.org
  - urls: 19: https://depmap.org/portal/api/no-captcha/download/files

### diffdock

- [SKILL.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/diffdock/SKILL.md):
  - hosts: 22: github.com; 32: github.com; 206: github.com; 208: huggingface.co; 213: arxiv.org; 214: arxiv.org; 224: doi.org; 226: arxiv.org; 228: arxiv.org; 229: export.arxiv.org
  - shell: 31: \`\`\`bash; 43: \`\`\`bash; 57: \`\`\`bash; 84: \`\`\`bash; 121: \`\`\`bash; 150: \`\`\`bash; 162: \`\`\`bash
  - urls: 22: https://github.com/gcorso/DiffDock/releases/tag/v1.1.3; 32: https://github.com/gcorso/DiffDock.git; 206: https://github.com/gcorso/DiffDock/tree/v1.1.3/app; 208: https://huggingface.co/spaces/reginabarzilaygroup/DiffDock-Web; 213: https://arxiv.org/abs/2210.01776; 214: https://arxiv.org/abs/2402.18396; 224: https://doi.org/10.48550/arXiv.2609.00065; 226: https://arxiv.org/abs/2609.00065; 228: https://arxiv.org/abs/2609.00065; 229: http://export.arxiv.org/api/query?id_list=2609.00065
- [assets/batch_template.csv](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/diffdock/assets/batch_template.csv): no matches
- [assets/custom_inference_config.yaml](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/diffdock/assets/custom_inference_config.yaml): no matches
- [references/confidence_and_limitations.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/diffdock/references/confidence_and_limitations.md):
  - hosts: 73: github.com; 74: github.com; 75: arxiv.org; 76: arxiv.org; 77: posebusters.readthedocs.io
  - urls: 73: https://github.com/gcorso/DiffDock/blob/v1.1.3/README.md; 74: https://github.com/gcorso/DiffDock/blob/v1.1.3/utils/inference_utils.py; 75: https://arxiv.org/abs/2402.18396; 76: https://arxiv.org/abs/2210.01776; 77: https://posebusters.readthedocs.io/en/latest/
- [references/parameters_reference.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/diffdock/references/parameters_reference.md):
  - hosts: 78: github.com; 79: github.com; 80: github.com; 81: github.com
  - urls: 78: https://github.com/gcorso/DiffDock/blob/v1.1.3/inference.py; 79: https://github.com/gcorso/DiffDock/blob/v1.1.3/default_inference_args.yaml; 80: https://github.com/gcorso/DiffDock/blob/v1.1.3/utils/inference_utils.py; 81: https://github.com/gcorso/DiffDock/blob/v1.1.3/datasets/esm_embedding_preparation.py
- [references/workflows_examples.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/diffdock/references/workflows_examples.md):
  - hosts: 73: github.com; 100: localhost:7860; 108: github.com; 109: github.com; 110: github.com; 111: docs.openmm.org
  - shell: 37: \`\`\`bash; 76: \`\`\`bash; 96: \`\`\`bash
  - urls: 73: https://github.com/gnina/gnina; 100: http://localhost:7860; 108: https://github.com/gcorso/DiffDock/blob/v1.1.3/inference.py; 109: https://github.com/gcorso/DiffDock/blob/v1.1.3/app/main.py; 110: https://github.com/gnina/gnina; 111: https://docs.openmm.org/latest/userguide/application/02_running_sims.html
- [scripts/analyze_results.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/diffdock/scripts/analyze_results.py): no matches
- [scripts/prepare_batch_csv.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/diffdock/scripts/prepare_batch_csv.py): no matches
- [scripts/setup_check.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/diffdock/scripts/setup_check.py):
  - hosts: 192: github.com; 207: github.com
  - urls: 192: https://github.com/gcorso/DiffDock.git; 207: https://github.com/gcorso/DiffDock

### esm

- [SKILL.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/esm/SKILL.md):
  - env: 5: ESM_API_KEY; 141: ESM_API_KEY; 157: ESM_API_KEY
  - environment_access: 157: os.environ
  - hosts: 19: biohub.ai; 142: biohub.ai; 156: biohub.ai; 197: biohub.org; 207: doi.org; 209: arxiv.org; 211: arxiv.org; 212: export.arxiv.org
  - install: 33: uv pip install
  - shell: 31: \`\`\`bash
  - urls: 19: https://biohub.ai; 142: https://biohub.ai/developer-console/api-keys; 156: https://biohub.ai; 197: https://biohub.org/acceptable-use-policy/; 207: https://doi.org/10.48550/arXiv.2609.00065; 209: https://arxiv.org/abs/2609.00065; 211: https://arxiv.org/abs/2609.00065; 212: http://export.arxiv.org/api/query?id_list=2609.00065
- [references/biohub-platform.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/esm/references/biohub-platform.md):
  - env: 32: ESM_API_KEY
  - environment_access: 32: os.environ
  - hosts: 31: biohub.ai; 103: github.com; 104: huggingface.co; 105: github.com; 106: github.com; 107: github.com
  - urls: 31: https://biohub.ai; 103: https://github.com/Biohub/esm; 104: https://huggingface.co/biohub/ESMFold2; 105: https://github.com/Biohub/esm/blob/main/esm/sdk/forge.py; 106: https://github.com/Biohub/esm/blob/main/esm/utils/structure/input_builder.py; 107: https://github.com/Biohub/esm/blob/main/esm/sdk/api.py
- [references/esm-c-api.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/esm/references/esm-c-api.md):
  - env: 90: ESM_API_KEY
  - environment_access: 90: os.environ
  - hosts: 89: biohub.ai; 139: pypi.org; 140: github.com; 141: github.com; 142: github.com; 143: huggingface.co
  - urls: 89: https://biohub.ai; 139: https://pypi.org/project/esm/3.4.1.post1/; 140: https://github.com/Biohub/esm/blob/main/esm/models/esmc/model.py; 141: https://github.com/Biohub/esm/blob/main/esm/models/esmc/tokenizer.py; 142: https://github.com/Biohub/esm/blob/main/esm/models/esmc/compatibility.py; 143: https://huggingface.co/biohub/ESMC-6B
- [references/esm3-api.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/esm/references/esm3-api.md):
  - hosts: 121: github.com; 122: github.com; 123: github.com; 124: github.com; 125: github.com
  - urls: 121: https://github.com/Biohub/esm/blob/main/_assets/ESM3_README.md; 122: https://github.com/Biohub/esm/blob/main/esm/sdk/api.py; 123: https://github.com/Biohub/esm/blob/main/esm/utils/generation.py; 124: https://github.com/Biohub/esm/blob/main/esm/utils/types.py; 125: https://github.com/Biohub/esm/blob/main/esm/tokenization/function_tokenizer.py
- [references/forge-api.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/esm/references/forge-api.md):
  - env: 9: ESM_API_KEY; 94: ESM_API_KEY
  - environment_access: 9: os.environ; 94: os.environ
  - hosts: 5: biohub.ai; 12: biohub.ai; 38: biohub.ai; 93: biohub.ai; 126: github.com; 127: github.com; 128: github.com; 129: github.com; 130: github.com
  - urls: 5: https://biohub.ai; 12: https://biohub.ai/developer-console/api-keys; 38: https://biohub.ai; 93: https://biohub.ai; 126: https://github.com/Biohub/esm/blob/main/esm/sdk/__init__.py; 127: https://github.com/Biohub/esm/blob/main/esm/sdk/forge.py; 128: https://github.com/Biohub/esm/blob/main/esm/sdk/base_forge_client.py; 129: https://github.com/Biohub/esm/blob/main/esm/sdk/retry.py; 130: https://github.com/Biohub/esm/blob/main/esm/utils/forge_context_manager.py
- [references/review.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/esm/references/review.md):
  - hosts: 12: pypi.org; 13: github.com; 14: github.com; 15: github.com; 16: github.com; 17: github.com; 18: github.com; 19: github.com; 20: github.com; 21: github.com; 22: huggingface.co; 23: github.com; 24: scikit-learn.org
  - urls: 12: https://pypi.org/project/esm/3.4.1.post1/; 12: https://pypi.org/pypi/esm/3.4.1.post1/json; 13: https://github.com/Biohub/esm; 14: https://github.com/Biohub/esm/blob/main/_assets/ESM3_README.md; 15: https://github.com/Biohub/esm/blob/main/esm/sdk/__init__.py; 16: https://github.com/Biohub/esm/blob/main/esm/sdk/api.py; 17: https://github.com/Biohub/esm/blob/main/esm/sdk/forge.py; 18: https://github.com/Biohub/esm/blob/main/esm/sdk/base_forge_client.py; 18: https://github.com/Biohub/esm/blob/main/esm/sdk/retry.py; 19: https://github.com/Biohub/esm/blob/main/esm/models/esmc/model.py; 19: https://github.com/Biohub/esm/blob/main/esm/models/esmc/tokenizer.py; 19: https://github.com/Biohub/esm/blob/main/esm/models/esmc/compatibility.py; 20: https://github.com/Biohub/esm/blob/main/esm/utils/generation.py; 20: https://github.com/Biohub/esm/blob/main/esm/tokenization/function_tokenizer.py; 20: https://github.com/Biohub/esm/blob/main/esm/utils/types.py; 21: https://github.com/Biohub/esm/blob/main/esm/utils/structure/input_builder.py; 22: https://huggingface.co/biohub/ESMC-300M; 22: https://huggingface.co/biohub/ESMC-600M; 22: https://huggingface.co/biohub/ESMC-6B; 22: https://huggingface.co/biohub/ESMFold2; 23: https://github.com/facebookresearch/esm; 24: https://scikit-learn.org/stable/common_pitfalls.html; 24: https://scikit-learn.org/stable/modules/generated/sklearn.decomposition.PCA.html; 24: https://scikit-learn.org/stable/modules/generated/sklearn.cluster.KMeans.html
- [references/workflows.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/esm/references/workflows.md):
  - hosts: 137: github.com; 138: github.com; 139: scikit-learn.org; 140: scikit-learn.org; 141: scikit-learn.org
  - urls: 137: https://github.com/Biohub/esm/blob/main/_assets/ESM3_README.md; 138: https://github.com/Biohub/esm/blob/main/esm/models/esmc/model.py; 139: https://scikit-learn.org/stable/common_pitfalls.html; 140: https://scikit-learn.org/stable/modules/generated/sklearn.decomposition.PCA.html; 141: https://scikit-learn.org/stable/modules/generated/sklearn.cluster.KMeans.html
- [scripts/esm_embeddings.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/esm/scripts/esm_embeddings.py): no matches

### gget

- [SKILL.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/gget/SKILL.md):
  - hosts: 101: github.com; 109: gget.info; 166: scverse.org; 167: github.com; 168: doi.org; 178: doi.org; 180: arxiv.org; 182: arxiv.org; 183: export.arxiv.org
  - install: 30: uv pip install; 125: uv pip install
  - shell: 26: \`\`\`bash; 41: \`\`\`bash
  - urls: 101: https://github.com/scverse/gget/blob/main/gget/gget_enrichr.py; 166: https://scverse.org/gget/; 167: https://github.com/scverse/gget/issues; 168: https://doi.org/10.1093/bioinformatics/btac836; 178: https://doi.org/10.48550/arXiv.2609.00065; 180: https://arxiv.org/abs/2609.00065; 182: https://arxiv.org/abs/2609.00065; 183: http://export.arxiv.org/api/query?id_list=2609.00065
- [references/common_workflows.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/gget/references/common_workflows.md):
  - shell: 20: \`\`\`bash
- [references/database_info.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/gget/references/database_info.md):
  - hosts: 3: github.com; 4: scverse.org; 14: ftp.ensembl.org; 14: ftp.ensemblgenomes.org; 15: mysql-eg-publicsql.ebi.ac.uk; 18: files.rcsb.org; 18: data.rcsb.org; 19: g2p.broadinstitute.org; 20: blast.ncbi.nlm.nih.gov; 21: genome.ucsc.edu; 23: elm.eu.org; 29: rest.ensembl.org; 39: maayanlab.cloud; 40: maayanlab.cloud; 42: maayanlab.cloud; 43: maayanlab.cloud; 44: bgee.org; 45: api.platform.opentargets.org; 46: www.cbioportal.org; 60: scverse.org; 61: github.com; 62: github.com; 63: scverse.org; 69: cancer.sanger.ac.uk; 86: eightcubedb.onrender.com; 117: doi.org
  - urls: 3: https://github.com/scverse/gget/tree/v0.30.8/gget; 4: https://scverse.org/gget/; 19: https://g2p.broadinstitute.org/api/gene/{gene}/protein/{accession}/protein-features; 20: https://blast.ncbi.nlm.nih.gov/Blast.cgi; 20: https://blast.ncbi.nlm.nih.gov/doc/blast-help/developerinfo.html; 21: https://genome.ucsc.edu/cgi-bin/hgBlat; 29: https://rest.ensembl.org/; 39: https://maayanlab.cloud/matrixapi/coltop; 40: https://maayanlab.cloud/archs4/search/loadExpressionTissue.php?search={symbol}&species={human\|mouse}&type=tissue; 42: https://maayanlab.cloud/speedrichr/api/addList; 44: https://bgee.org/api/; 45: https://api.platform.opentargets.org/api/v4/graphql; 46: https://www.cbioportal.org/api/v2/api-docs; 60: https://scverse.org/gget/en/opentargets.html; 61: https://github.com/scverse/gget/blob/v0.30.8/gget/gget_opentargets.py; 62: https://github.com/scverse/gget/blob/v0.30.8/gget/gget_enrichr.py; 63: https://scverse.org/gget/en/cellxgene.html; 69: https://cancer.sanger.ac.uk/api/mono/products/v1/downloads/scripted; 86: https://eightcubedb.onrender.com/; 117: https://doi.org/10.1093/bioinformatics/btac836
- [references/module_catalog.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/gget/references/module_catalog.md):
  - env: 603: COSMIC_EMAIL; 604: COSMIC_PASSWORD; 719: OPENAI_API_KEY
  - environment_access: 603: os.environ; 604: os.environ
  - hosts: 95: gget.info; 281: scverse.org
  - install: 742: uv pip install; 742: pip install
  - provider_key: 719: OPENAI_API_KEY
  - shell: 26: \`\`\`bash; 59: \`\`\`bash; 85: \`\`\`bash; 110: \`\`\`bash; 141: \`\`\`bash; 166: \`\`\`bash; 190: \`\`\`bash; 218: \`\`\`bash; 246: \`\`\`bash; 269: \`\`\`bash; 288: \`\`\`bash; 305: \`\`\`bash; 326: \`\`\`bash; 342: \`\`\`bash; 372: \`\`\`bash; 390: \`\`\`bash; 407: \`\`\`bash; 443: \`\`\`bash; 469: \`\`\`bash; 503: \`\`\`bash; 533: \`\`\`bash; 552: \`\`\`bash; 587: \`\`\`bash; 630: \`\`\`bash; 661: \`\`\`bash; 696: \`\`\`bash; 715: \`\`\`bash; 756: \`\`\`bash
  - urls: 281: https://scverse.org/gget/en/g2p.html
- [references/module_reference.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/gget/references/module_reference.md):
  - env: 517: OPENAI_API_KEY; 527: OPENAI_API_KEY
  - home_paths: 210: ~/tmp/jackhmmer
  - hosts: 3: github.com; 193: scverse.org
  - outside_writes: 0: potential home/cache write: home-derived path and write/download/dataset operation in this file
  - provider_key: 517: OPENAI_API_KEY; 527: OPENAI_API_KEY
  - urls: 3: https://github.com/scverse/gget/tree/v0.30.8/gget; 193: https://scverse.org/gget/en/g2p.html
- [references/workflows.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/gget/references/workflows.md):
  - hosts: 27: gget.info
  - shell: 111: \`\`\`bash; 197: \`\`\`bash
- [scripts/batch_sequence_analysis.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/gget/scripts/batch_sequence_analysis.py): no matches
- [scripts/enrichment_pipeline.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/gget/scripts/enrichment_pipeline.py): no matches
- [scripts/gene_analysis.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/gget/scripts/gene_analysis.py):
  - hosts: 63: gget.info

### latchbio-integration

- [SKILL.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/latchbio-integration/SKILL.md):
  - home_paths: 78: ~/.latch/token
  - hosts: 231: wiki.latch.bio; 232: wiki.latch.bio; 233: wiki.latch.bio; 234: pypi.org; 235: github.com; 236: github.com; 237: console.latch.bio; 247: doi.org; 249: arxiv.org; 251: arxiv.org; 252: export.arxiv.org
  - install: 72: uv pip install
  - shell: 69: \`\`\`bash; 80: \`\`\`bash; 87: \`\`\`bash; 97: subprocess; 99: \`\`\`bash; 100: subprocess; 161: \`\`\`bash; 171: \`\`\`bash; 177: \`\`\`bash; 207: subprocess.run; 217: \`\`\`bash; 224: \`\`\`bash
  - urls: 231: https://wiki.latch.bio/llms.txt; 232: https://wiki.latch.bio/workflows/overview; 233: https://wiki.latch.bio/reference/sdk; 234: https://pypi.org/project/latch/; 235: https://github.com/latchbio/latch/tree/b3768e65c6d496868f6e530f11977d857ad85dc7; 236: https://github.com/latchbio/latch/blob/b3768e65c6d496868f6e530f11977d857ad85dc7/CHANGELOG.md; 237: https://console.latch.bio; 247: https://doi.org/10.48550/arXiv.2609.00065; 249: https://arxiv.org/abs/2609.00065; 251: https://arxiv.org/abs/2609.00065; 252: http://export.arxiv.org/api/query?id_list=2609.00065
- [references/data-management.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/latchbio-integration/references/data-management.md):
  - home_paths: 100: ~/.latch/lpath/
  - hosts: 260: wiki.latch.bio; 261: wiki.latch.bio; 262: wiki.latch.bio; 263: wiki.latch.bio; 264: wiki.latch.bio; 265: github.com
  - outside_writes: 0: potential home/cache write: home-derived path and write/download/dataset operation in this file
  - shell: 218: \`\`\`bash; 226: \`\`\`bash
  - urls: 36: latch:///path/in/current-workspace; 37: latch://12345.account/path/in/workspace; 38: latch://shared/path/to/shared-data; 39: latch://67890.node; 42: latch:///; 63: latch:///welcome; 95: latch:///inputs/design.csv; 121: latch:///results/run-001; 136: latch:///results/run-001/report.txt; 137: latch:///archive/run-001/report.txt; 144: latch:///scratch/run-001; 174: latch:///results/summary.txt; 211: latch:///results/fastq/; 228: latch:///inputs; 231: latch:///inputs/sample.fastq.gz; 232: latch:///results/report.html; 235: latch:///results/run-001; 238: latch:///results/run-001; 241: latch:///scratch/run-001; 260: https://wiki.latch.bio/workflows/sdk/api/working-with-files; 261: https://wiki.latch.bio/workflows/sdk/python/legacy-file-support; 262: https://wiki.latch.bio/workflows/sdk/python/latch-urls; 263: https://wiki.latch.bio/data/data-command-line; 264: https://wiki.latch.bio/data/overview; 265: https://github.com/latchbio/latch/blob/b3768e65c6d496868f6e530f11977d857ad85dc7/src/latch/ldata/path.py
- [references/latch-mcp.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/latchbio-integration/references/latch-mcp.md):
  - hosts: 6: mcp.latch.bio; 33: mcp.latch.bio; 45: mcp.latch.bio; 53: mcp.latch.bio; 161: wiki.latch.bio
  - shell: 44: \`\`\`bash; 52: \`\`\`bash
  - urls: 6: https://mcp.latch.bio/mcp; 33: https://mcp.latch.bio/mcp; 45: https://mcp.latch.bio/mcp; 53: https://mcp.latch.bio/mcp; 161: https://wiki.latch.bio/agent/latch-mcp
- [references/nextflow-snakemake.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/latchbio-integration/references/nextflow-snakemake.md):
  - hosts: 249: wiki.latch.bio; 250: wiki.latch.bio; 251: wiki.latch.bio; 252: wiki.latch.bio; 253: wiki.latch.bio; 254: wiki.latch.bio; 255: wiki.latch.bio; 256: wiki.latch.bio; 257: github.com; 258: github.com
  - install: 19: uv pip install; 147: uv pip install; 183: uv pip install
  - shell: 18: \`\`\`bash; 24: \`\`\`bash; 49: \`\`\`bash; 72: \`\`\`bash; 85: \`\`\`bash; 112: \`\`\`bash; 144: \`\`\`bash; 152: \`\`\`bash; 158: \`\`\`bash; 164: \`\`\`bash; 180: \`\`\`bash; 194: \`\`\`bash
  - urls: 249: https://wiki.latch.bio/workflows/sdk/nextflow/tutorial; 250: https://wiki.latch.bio/workflows/sdk/nextflow/overview; 251: https://wiki.latch.bio/workflows/sdk/nextflow/dependencies; 252: https://wiki.latch.bio/workflows/sdk/nextflow/profiles; 253: https://wiki.latch.bio/workflows/sdk/nextflow/gpus; 254: https://wiki.latch.bio/workflows/sdk/nextflow/shared-storage; 255: https://wiki.latch.bio/workflows/sdk/snakemake-v2/tutorial; 256: https://wiki.latch.bio/workflows/sdk/snakemake-v2/overview; 257: https://github.com/latchbio/latch/blob/b3768e65c6d496868f6e530f11977d857ad85dc7/src/latch_cli/main.py; 258: https://github.com/latchbio/latch/blob/b3768e65c6d496868f6e530f11977d857ad85dc7/CHANGELOG.md
- [references/operations-and-debugging.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/latchbio-integration/references/operations-and-debugging.md):
  - env: 329: PATH
  - home_paths: 22: ~/.latch/token
  - hosts: 349: wiki.latch.bio; 350: wiki.latch.bio; 351: wiki.latch.bio; 352: wiki.latch.bio; 353: wiki.latch.bio; 354: wiki.latch.bio; 355: github.com
  - shell: 7: \`\`\`bash; 14: \`\`\`bash; 29: \`\`\`bash; 35: \`\`\`bash; 41: \`\`\`bash; 47: \`\`\`bash; 89: \`\`\`bash; 109: \`\`\`bash; 120: \`\`\`bash; 126: \`\`\`bash; 149: \`\`\`bash; 155: \`\`\`bash; 283: \`\`\`bash; 302: \`\`\`bash
  - urls: 18: latch:///; 179: latch:///test-data/reads.fastq.gz; 349: https://wiki.latch.bio/workflows/sdk/cli/commands; 350: https://wiki.latch.bio/workflows/sdk/testing-and-debugging-a-workflow/development-and-debugging; 351: https://wiki.latch.bio/workflows/sdk/testing-and-debugging-a-workflow/programmatic-execution; 352: https://wiki.latch.bio/workflows/sdk/console/execution-monitoring; 353: https://wiki.latch.bio/workflows/sdk/console/resource-monitoring; 354: https://wiki.latch.bio/workflows/sdk/console/versioning; 355: https://github.com/latchbio/latch/blob/b3768e65c6d496868f6e530f11977d857ad85dc7/src/latch_cli/main.py
- [references/registry.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/latchbio-integration/references/registry.md):
  - hosts: 273: wiki.latch.bio; 274: wiki.latch.bio; 275: wiki.latch.bio; 276: wiki.latch.bio; 277: wiki.latch.bio; 278: wiki.latch.bio; 279: github.com
  - install: 92: uv pip install
  - shell: 91: \`\`\`bash
  - urls: 147: latch:///inputs/sample-001.fastq.gz; 167: latch:///inputs/sample-002.fastq.gz; 273: https://wiki.latch.bio/registry/sdk/latch-sdk-registry-integration; 274: https://wiki.latch.bio/registry/sdk/account-objects; 275: https://wiki.latch.bio/registry/sdk/registry-projects; 276: https://wiki.latch.bio/registry/sdk/table-objects; 277: https://wiki.latch.bio/registry/sdk/record-objects; 278: https://wiki.latch.bio/workflows/sdk/api/registry-usage-tutorial; 279: https://github.com/latchbio/latch/tree/b3768e65c6d496868f6e530f11977d857ad85dc7/src/latch/registry
- [references/resource-configuration.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/latchbio-integration/references/resource-configuration.md):
  - hosts: 276: wiki.latch.bio; 277: wiki.latch.bio; 278: github.com; 279: github.com
  - urls: 276: https://wiki.latch.bio/workflows/sdk/python/defining-cloud-resources; 277: https://wiki.latch.bio/workflows/sdk/console/resource-monitoring; 278: https://github.com/latchbio/latch/blob/b3768e65c6d496868f6e530f11977d857ad85dc7/src/latch/resources/tasks.py; 279: https://github.com/latchbio/latch/blob/b3768e65c6d496868f6e530f11977d857ad85dc7/CHANGELOG.md
- [references/ui-and-automation.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/latchbio-integration/references/ui-and-automation.md):
  - hosts: 25: github.com; 27: example.org; 28: github.com; 354: wiki.latch.bio; 355: wiki.latch.bio; 356: wiki.latch.bio; 357: wiki.latch.bio; 358: wiki.latch.bio; 359: wiki.latch.bio; 360: wiki.latch.bio
  - urls: 25: https://github.com/example; 27: https://example.org/docs/rnaseq-qc; 28: https://github.com/example/rnaseq-qc; 187: latch:///test-data/example.fastq.gz; 192: latch:///test-results/rnaseq-qc; 354: https://wiki.latch.bio/workflows/sdk/ui/latch-metadata; 355: https://wiki.latch.bio/workflows/sdk/ui/launch-plans; 356: https://wiki.latch.bio/workflows/sdk/ui/messages; 357: https://wiki.latch.bio/workflows/sdk/ui/results; 358: https://wiki.latch.bio/workflows/sdk/automation/overview; 359: https://wiki.latch.bio/workflows/sdk/automation/example-data-addition; 360: https://wiki.latch.bio/workflows/sdk/automation/example-interval
- [references/verified-workflows.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/latchbio-integration/references/verified-workflows.md):
  - hosts: 162: console.latch.bio; 222: wiki.latch.bio; 223: wiki.latch.bio; 224: github.com; 225: wiki.latch.bio; 226: github.com
  - shell: 47: \`\`\`bash; 54: \`\`\`bash
  - urls: 162: https://console.latch.bio/workflows; 222: https://wiki.latch.bio/workflows/overview; 223: https://wiki.latch.bio/llms.txt; 224: https://github.com/latchbio/latch/tree/b3768e65c6d496868f6e530f11977d857ad85dc7/src/latch/verified; 225: https://wiki.latch.bio/agent/latch-mcp; 226: https://github.com/latch-verified
- [references/workflow-creation.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/latchbio-integration/references/workflow-creation.md):
  - hosts: 129: github.com; 251: wiki.latch.bio; 286: wiki.latch.bio; 287: wiki.latch.bio; 288: wiki.latch.bio; 289: wiki.latch.bio; 290: wiki.latch.bio; 291: wiki.latch.bio; 292: github.com
  - shell: 19: \`\`\`bash; 20: subprocess; 24: subprocess
  - urls: 129: https://github.com/example/fastq-validator; 251: https://wiki.latch.bio/workflows/sdk/python/caching; 286: https://wiki.latch.bio/workflows/sdk/python/overview; 287: https://wiki.latch.bio/workflows/sdk/python/quick-start; 288: https://wiki.latch.bio/workflows/sdk/python/conditional-sections; 289: https://wiki.latch.bio/workflows/sdk/python/map-task; 290: https://wiki.latch.bio/workflows/sdk/python/caching; 291: https://wiki.latch.bio/workflows/sdk/python/workflow-environment/overview; 292: https://github.com/latchbio/latch/tree/b3768e65c6d496868f6e530f11977d857ad85dc7
- [scripts/inspect_latch_sdk.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/latchbio-integration/scripts/inspect_latch_sdk.py): no matches

### medchem

- [SKILL.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/medchem/SKILL.md):
  - hosts: 17: github.com; 336: medchem-docs.datamol.io; 337: github.com; 338: pypi.org; 348: doi.org; 350: arxiv.org; 352: arxiv.org; 353: export.arxiv.org
  - install: 34: uv pip install
  - shell: 33: \`\`\`bash; 39: \`\`\`bash; 329: \`\`\`bash
  - urls: 17: https://github.com/datamol-io/medchem; 336: https://medchem-docs.datamol.io/; 337: https://github.com/datamol-io/medchem; 338: https://pypi.org/project/medchem/; 348: https://doi.org/10.48550/arXiv.2609.00065; 350: https://arxiv.org/abs/2609.00065; 352: https://arxiv.org/abs/2609.00065; 353: http://export.arxiv.org/api/query?id_list=2609.00065
- [references/api_guide.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/medchem/references/api_guide.md):
  - hosts: 3: medchem-docs.datamol.io; 111: dx.doi.org; 361: github.com; 361: medchem-docs.datamol.io; 362: medchem-docs.datamol.io; 363: medchem-docs.datamol.io; 364: github.com
  - urls: 3: https://medchem-docs.datamol.io/stable/api/medchem.rules.html; 111: https://dx.doi.org/10.1021/acs.jmedchem.0c01332; 361: https://github.com/datamol-io/medchem/releases/tag/2.1.1; 361: https://medchem-docs.datamol.io/stable/migration.html; 362: https://medchem-docs.datamol.io/stable/api/medchem.structural.html; 362: https://medchem-docs.datamol.io/stable/api/medchem.functional.html; 362: https://medchem-docs.datamol.io/stable/api/medchem.catalogs.html; 363: https://medchem-docs.datamol.io/stable/api/medchem.groups.html; 363: https://medchem-docs.datamol.io/stable/api/medchem.complexity.html; 363: https://medchem-docs.datamol.io/stable/api/medchem.constraints.html; 363: https://medchem-docs.datamol.io/stable/api/medchem.query.html; 364: https://github.com/datamol-io/medchem/tree/2.1.1/medchem
- [references/rules_catalog.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/medchem/references/rules_catalog.md):
  - hosts: 5: github.com; 5: medchem-docs.datamol.io; 57: pubmed.ncbi.nlm.nih.gov; 83: pubmed.ncbi.nlm.nih.gov; 173: dx.doi.org; 328: doi.org; 331: pubmed.ncbi.nlm.nih.gov
  - urls: 5: https://github.com/datamol-io/medchem/blob/2.1.1/medchem/rules/basic_rules.py; 5: https://medchem-docs.datamol.io/stable/api/medchem.rules.html; 57: https://pubmed.ncbi.nlm.nih.gov/12669025/; 83: https://pubmed.ncbi.nlm.nih.gov/10756480/; 173: https://dx.doi.org/10.1021/acs.jmedchem.0c01332; 328: https://doi.org/10.1023/a:1008130001697; 331: https://pubmed.ncbi.nlm.nih.gov/12669025/
- [scripts/filter_molecules.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/medchem/scripts/filter_molecules.py):
  - install: 24: uv pip install

### molfeat

- [SKILL.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/molfeat/SKILL.md):
  - hosts: 25: github.com; 160: github.com; 161: pypi.org; 162: github.com; 174: doi.org; 176: arxiv.org; 178: arxiv.org; 179: export.arxiv.org
  - install: 36: uv pip install
  - shell: 34: \`\`\`bash
  - urls: 25: https://github.com/datamol-io/molfeat/blob/1.0.0/docs/migration.md; 160: https://github.com/datamol-io/molfeat/releases/tag/1.0.0; 161: https://pypi.org/project/molfeat/1.0.0/; 162: https://github.com/datamol-io/molfeat/tree/1.0.0/molfeat; 174: https://doi.org/10.48550/arXiv.2609.00065; 176: https://arxiv.org/abs/2609.00065; 178: https://arxiv.org/abs/2609.00065; 179: http://export.arxiv.org/api/query?id_list=2609.00065
- [references/api_reference.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/molfeat/references/api_reference.md):
  - hosts: 3: github.com; 128: fs.molfeat.datamol.io
  - urls: 3: https://github.com/datamol-io/molfeat/tree/1.0.0/molfeat; 128: https://fs.molfeat.datamol.io/artifacts/
- [references/available_featurizers.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/molfeat/references/available_featurizers.md):
  - hosts: 4: github.com; 5: github.com; 75: github.com; 76: huggingface.co; 77: github.com
  - urls: 4: https://github.com/datamol-io/molfeat/tree/1.0.0/molfeat/calc; 5: https://github.com/datamol-io/molfeat/tree/1.0.0/molfeat/trans/pretrained; 75: https://github.com/datamol-io/molfeat/blob/1.0.0/docs/foundation_models.md; 76: https://huggingface.co/DeepChem/ChemBERTa-77M-MLM/blob/main/config.json; 77: https://github.com/reymond-group/map4/blob/master/map4/map4.py
- [references/choosing_a_featurizer.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/molfeat/references/choosing_a_featurizer.md): no matches
- [references/examples.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/molfeat/references/examples.md): no matches

### opentrons-integration

- [SKILL.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/opentrons-integration/SKILL.md):
  - hosts: 254: docs.opentrons.com; 347: doi.org; 349: arxiv.org; 351: arxiv.org; 352: export.arxiv.org
  - install: 114: uv pip install
  - shell: 97: \`\`\`bash; 103: \`\`\`bash; 112: \`\`\`bash
  - urls: 254: https://docs.opentrons.com/python-api/complex-commands/parameters/; 347: https://doi.org/10.48550/arXiv.2609.00065; 349: https://arxiv.org/abs/2609.00065; 351: https://arxiv.org/abs/2609.00065; 352: http://export.arxiv.org/api/query?id_list=2609.00065
- [references/api_reference.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/opentrons-integration/references/api_reference.md):
  - hosts: 5: docs.opentrons.com; 53: docs.opentrons.com; 75: docs.opentrons.com; 91: docs.opentrons.com; 208: docs.opentrons.com; 364: docs.opentrons.com
  - shell: 384: \`\`\`bash
  - urls: 5: https://docs.opentrons.com/python-api/reference/protocols/; 53: https://docs.opentrons.com/python-api/versioning/; 75: https://docs.opentrons.com/python-api/pipettes/volume-modes/; 91: https://docs.opentrons.com/python-api/pipettes/loading/; 208: https://docs.opentrons.com/python-api/reference/instruments/; 364: https://docs.opentrons.com/python-api/pipettes/partial-tip-pickup/
- [references/liquid_handling.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/opentrons-integration/references/liquid_handling.md):
  - hosts: 387: docs.opentrons.com
  - urls: 387: https://docs.opentrons.com/python-api/pipettes/partial-tip-pickup/
- [references/migration-api-2-19-to-2-29.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/opentrons-integration/references/migration-api-2-19-to-2-29.md): no matches
- [references/modules_and_deck.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/opentrons-integration/references/modules_and_deck.md):
  - hosts: 30: docs.opentrons.com; 31: docs.opentrons.com; 189: docs.opentrons.com
  - urls: 30: https://docs.opentrons.com/flex/modules/; 31: https://docs.opentrons.com/ot-2/modules/; 189: https://docs.opentrons.com/thermocycler/lid-seals/
- [references/protocol_authoring.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/opentrons-integration/references/protocol_authoring.md):
  - hosts: 145: labware.opentrons.com
  - urls: 145: https://labware.opentrons.com/
- [references/sources.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/opentrons-integration/references/sources.md):
  - hosts: 11: pypi.org; 41: docs.opentrons.com; 43: docs.opentrons.com; 46: docs.opentrons.com; 48: docs.opentrons.com; 49: docs.opentrons.com; 51: docs.opentrons.com; 53: docs.opentrons.com; 58: docs.opentrons.com; 61: docs.opentrons.com; 63: docs.opentrons.com; 65: docs.opentrons.com; 68: docs.opentrons.com; 71: docs.opentrons.com; 73: docs.opentrons.com; 75: docs.opentrons.com; 80: docs.opentrons.com; 82: docs.opentrons.com; 84: docs.opentrons.com; 86: docs.opentrons.com; 88: docs.opentrons.com; 90: docs.opentrons.com; 92: labware.opentrons.com; 97: docs.opentrons.com; 99: docs.opentrons.com; 101: docs.opentrons.com; 103: docs.opentrons.com; 105: docs.opentrons.com; 107: docs.opentrons.com; 109: docs.opentrons.com; 111: docs.opentrons.com; 113: docs.opentrons.com; 115: docs.opentrons.com; 120: docs.opentrons.com; 123: docs.opentrons.com; 125: docs.opentrons.com; 127: docs.opentrons.com; 129: docs.opentrons.com; 131: opentrons.com; 136: pypi.org; 139: github.com; 141: github.com; 143: github.com; 144: github.com; 146: github.com; 154: docs.opentrons.com
  - urls: 11: https://pypi.org/project/opentrons/; 41: https://docs.opentrons.com/python-api/; 43: https://docs.opentrons.com/python-api/tutorial/; 46: https://docs.opentrons.com/python-api/versioning/; 48: https://docs.opentrons.com/python-api/reference/protocols/; 49: https://docs.opentrons.com/python-api/reference/instruments/; 51: https://docs.opentrons.com/python-api/examples/; 53: https://docs.opentrons.com/python-api/adapting-ot2-flex/; 58: https://docs.opentrons.com/python-api/pipettes/loading/; 61: https://docs.opentrons.com/python-api/pipettes/characteristics/; 63: https://docs.opentrons.com/python-api/pipettes/volume-modes/; 65: https://docs.opentrons.com/python-api/pipettes/partial-tip-pickup/; 68: https://docs.opentrons.com/python-api/building-block-commands/liquids/; 71: https://docs.opentrons.com/python-api/complex-commands/; 73: https://docs.opentrons.com/python-api/liquid-classes/using/; 75: https://docs.opentrons.com/python-api/liquid-class-definitions/; 80: https://docs.opentrons.com/python-api/runtime-parameters/; 82: https://docs.opentrons.com/python-api/runtime-parameters/defining/; 84: https://docs.opentrons.com/python-api/labware/; 86: https://docs.opentrons.com/python-api/moving-labware/; 88: https://docs.opentrons.com/python-api/deck-slots/; 90: https://docs.opentrons.com/python-api/groups/; 92: https://labware.opentrons.com/; 97: https://docs.opentrons.com/python-api/modules/setup/; 99: https://docs.opentrons.com/python-api/modules/absorbance-plate-reader/; 101: https://docs.opentrons.com/python-api/modules/flex-stacker/; 103: https://docs.opentrons.com/python-api/modules/heater-shaker/; 105: https://docs.opentrons.com/python-api/modules/magnetic-block/; 107: https://docs.opentrons.com/python-api/modules/magnetic-module/; 109: https://docs.opentrons.com/python-api/modules/temperature-module/; 111: https://docs.opentrons.com/python-api/modules/thermocycler/; 113: https://docs.opentrons.com/thermocycler/lid-seals/; 115: https://docs.opentrons.com/python-api/modules/concurrent/; 120: https://docs.opentrons.com/flex/; 123: https://docs.opentrons.com/flex/protocols/python-api/; 125: https://docs.opentrons.com/flex/modules/; 127: https://docs.opentrons.com/ot-2/; 129: https://docs.opentrons.com/ot-2/modules/; 131: https://opentrons.com/app/; 136: https://pypi.org/project/opentrons/; 139: https://github.com/Opentrons/opentrons/blob/edge/api/release-notes.md; 141: https://github.com/Opentrons/opentrons/releases; 143: https://github.com/Opentrons/opentrons/releases/tag/v10.0.0; 144: https://github.com/Opentrons/opentrons/blob/v10.0.0/api/src/opentrons/protocols/api_support/definitions.py; 146: https://github.com/Opentrons/opentrons; 154: https://docs.opentrons.com/http/api_reference.html
- [references/validation_and_operations.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/opentrons-integration/references/validation_and_operations.md):
  - install: 28: uv pip install
  - shell: 16: \`\`\`bash; 26: \`\`\`bash; 38: \`\`\`bash; 54: \`\`\`bash; 63: \`\`\`bash; 85: \`\`\`bash
- [requirements-flex.txt](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/opentrons-integration/requirements-flex.txt): no matches
- [requirements-ot2.txt](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/opentrons-integration/requirements-ot2.txt): no matches
- [scripts/absorbance_reader_template.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/opentrons-integration/scripts/absorbance_reader_template.py): no matches
- [scripts/basic_protocol_template.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/opentrons-integration/scripts/basic_protocol_template.py): no matches
- [scripts/ot2_basic_protocol_template.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/opentrons-integration/scripts/ot2_basic_protocol_template.py): no matches
- [scripts/pcr_setup_template.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/opentrons-integration/scripts/pcr_setup_template.py): no matches
- [scripts/runtime_parameters_template.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/opentrons-integration/scripts/runtime_parameters_template.py): no matches
- [scripts/serial_dilution_template.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/opentrons-integration/scripts/serial_dilution_template.py): no matches

### pathway-enrichment

- [SKILL.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/pathway-enrichment/SKILL.md):
  - hosts: 156: docs.gsea-msigdb.org; 223: gseapy.readthedocs.io; 223: github.com; 224: pypi.org; 225: maayanlab.cloud; 225: www.gsea-msigdb.org; 236: doi.org; 238: arxiv.org; 240: arxiv.org; 241: export.arxiv.org
  - install: 50: uv pip install
  - shell: 49: \`\`\`bash; 168: \`\`\`bash
  - urls: 156: https://docs.gsea-msigdb.org/GSEA/GSEA_FAQ/; 223: https://gseapy.readthedocs.io/; 223: https://github.com/zqfang/GSEApy; 224: https://biit.cs.ut.ee/gprofiler/; 224: https://pypi.org/project/gprofiler-official/; 225: https://maayanlab.cloud/Enrichr/; 225: https://www.gsea-msigdb.org/gsea/msigdb/; 236: https://doi.org/10.48550/arXiv.2609.00065; 238: https://arxiv.org/abs/2609.00065; 240: https://arxiv.org/abs/2609.00065; 241: http://export.arxiv.org/api/query?id_list=2609.00065
- [references/databases-and-gene-sets.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/pathway-enrichment/references/databases-and-gene-sets.md):
  - hosts: 62: www.gsea-msigdb.org; 169: decoupler.scverse.org
  - urls: 62: https://www.gsea-msigdb.org/gsea/msigdb; 169: https://decoupler.scverse.org/
- [references/gseapy.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/pathway-enrichment/references/gseapy.md): no matches
- [references/interpretation.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/pathway-enrichment/references/interpretation.md): no matches
- [references/verified-api.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/pathway-enrichment/references/verified-api.md):
  - hosts: 11: github.com; 12: github.com; 13: github.com; 14: gseapy.readthedocs.io; 15: maayanlab.cloud; 17: maayanlab.cloud; 30: maayanlab.cloud; 58: pypi.org; 86: www.gsea-msigdb.org; 87: www.gsea-msigdb.org; 88: www.gsea-msigdb.org; 89: github.com; 92: data.broadinstitute.org; 102: www.ensembl.org; 103: github.com; 104: docs.mygene.info; 105: github.com; 115: mygene.info; 125: docs.gsea-msigdb.org; 126: docs.gsea-msigdb.org; 127: decoupler.scverse.org
  - urls: 11: https://github.com/zqfang/GSEApy/releases/tag/v1.3.1; 12: https://github.com/zqfang/GSEApy/blob/v1.3.1/gseapy/enrichr.py; 13: https://github.com/zqfang/GSEApy/blob/v1.3.1/src/stats.rs; 14: https://gseapy.readthedocs.io/en/latest/run.html; 15: https://maayanlab.cloud/Enrichr/help#api; 17: https://maayanlab.cloud/Enrichr; 30: https://maayanlab.cloud/speedrichr/api; 56: https://biit.cs.ut.ee/gprofiler/page/apis; 57: https://biit.cs.ut.ee/gprofiler/page/docs; 58: https://pypi.org/project/gprofiler-official/1.0.0/; 61: https://biit.cs.ut.ee/gprofiler; 86: https://www.gsea-msigdb.org/gsea/msigdb; 87: https://www.gsea-msigdb.org/gsea/msigdb/human/collections.jsp; 88: https://www.gsea-msigdb.org/gsea/msigdb/mouse/collections.jsp; 89: https://github.com/zqfang/GSEApy/blob/v1.3.1/gseapy/msigdb.py; 92: https://data.broadinstitute.org/gsea-msigdb/msigdb/release/; 102: https://www.ensembl.org/info/data/biomart/biomart_restful.html; 103: https://github.com/zqfang/GSEApy/blob/v1.3.1/gseapy/biomart.py; 104: https://docs.mygene.info/en/latest/doc/query_service.html; 105: https://github.com/biothings/mygene.py; 115: https://mygene.info/v3/query; 125: https://docs.gsea-msigdb.org/GSEA/GSEA_User_Guide/; 126: https://docs.gsea-msigdb.org/GSEA/GSEA_FAQ/; 127: https://decoupler.scverse.org/en/latest/api/generated/decoupler.op.progeny.html
- [scripts/run_enrichment.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/pathway-enrichment/scripts/run_enrichment.py): no matches

### primekg

- [SKILL.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/primekg/SKILL.md):
  - env: 50: PWD
  - hosts: 22: github.com; 30: doi.org; 49: dataverse.harvard.edu; 152: doi.org; 153: doi.org; 163: doi.org; 165: arxiv.org; 167: arxiv.org; 168: export.arxiv.org
  - shell: 47: \`\`\`bash
  - urls: 22: https://github.com/mims-harvard/PrimeKG; 30: https://doi.org/10.7910/DVN/IXA7BM; 49: https://dataverse.harvard.edu/api/access/datafile/6180620; 152: https://doi.org/10.1038/s41597-023-01960-3; 153: https://doi.org/10.7910/DVN/IXA7BM; 163: https://doi.org/10.48550/arXiv.2609.00065; 165: https://arxiv.org/abs/2609.00065; 167: https://arxiv.org/abs/2609.00065; 168: http://export.arxiv.org/api/query?id_list=2609.00065
- [references/data-contract.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/primekg/references/data-contract.md):
  - hosts: 14: dataverse.harvard.edu; 61: dataverse.harvard.edu; 85: dataverse.harvard.edu; 87: github.com; 122: zitniklab.hms.harvard.edu; 123: github.com; 124: dataverse.harvard.edu; 125: guides.dataverse.org; 126: guides.dataverse.org; 127: pypi.org; 128: github.com; 129: github.com; 130: tdcommons.ai
  - shell: 12: \`\`\`bash
  - urls: 14: https://dataverse.harvard.edu/api/datasets/:persistentId/versions/:latest-published?persistentId=doi:10.7910/DVN/IXA7BM; 61: https://dataverse.harvard.edu/api/access/datafile/{file_id; 85: https://dataverse.harvard.edu/api/access/datafile/6191270; 87: https://github.com/mims-harvard/PrimeKG/blob/32a3818cf7ff981081c4887c20b2f733ad6ec0a6/knowledge_graph/build_graph.ipynb; 122: https://zitniklab.hms.harvard.edu/projects/PrimeKG/; 123: https://github.com/mims-harvard/PrimeKG; 124: https://dataverse.harvard.edu/api/datasets/:persistentId/versions/:latest-published?persistentId=doi:10.7910/DVN/IXA7BM; 125: https://guides.dataverse.org/en/latest/api/native-api.html; 126: https://guides.dataverse.org/en/latest/api/dataaccess.html; 127: https://pypi.org/pypi/PyTDC/1.1.15/json; 128: https://github.com/mims-harvard/TDC/blob/main/tdc/resource/primekg.py; 129: https://github.com/mims-harvard/TDC/blob/main/tdc/metadata.py; 130: https://tdcommons.ai/resources/overview/
- [scripts/query_primekg.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/primekg/scripts/query_primekg.py):
  - env: 13: PRIMEKG_DATA
  - environment_access: 13: os.environ.get
  - hosts: 25: doi.org
  - urls: 25: https://doi.org/10.7910/DVN/IXA7BM

### pydeseq2

- [SKILL.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/pydeseq2/SKILL.md):
  - hosts: 22: github.com; 172: doi.org; 174: arxiv.org; 176: arxiv.org; 177: export.arxiv.org
  - install: 59: uv pip install
  - shell: 57: \`\`\`bash; 66: \`\`\`bash
  - urls: 22: https://github.com/scverse/PyDESeq2/releases/tag/v0.5.4; 172: https://doi.org/10.48550/arXiv.2609.00065; 174: https://arxiv.org/abs/2609.00065; 176: https://arxiv.org/abs/2609.00065; 177: http://export.arxiv.org/api/query?id_list=2609.00065
- [references/analysis_patterns.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/pydeseq2/references/analysis_patterns.md):
  - hosts: 104: formulaic-contrasts.readthedocs.io; 105: formulaic-contrasts.readthedocs.io; 106: bioconductor.org
  - urls: 104: https://formulaic-contrasts.readthedocs.io/en/latest/contrasts.html; 105: https://formulaic-contrasts.readthedocs.io/en/latest/generated/formulaic_contrasts.FormulaicContrasts.html; 106: https://bioconductor.org/packages/release/bioc/vignettes/DESeq2/inst/doc/DESeq2.html#model-matrix-not-full-rank
- [references/api_reference.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/pydeseq2/references/api_reference.md):
  - hosts: 9: pypi.org; 137: raw.githubusercontent.com; 151: pydeseq2.readthedocs.io; 152: pydeseq2.readthedocs.io; 153: pydeseq2.readthedocs.io; 154: github.com; 155: github.com; 156: github.com; 157: github.com
  - urls: 9: https://pypi.org/project/pydeseq2/0.5.4/; 137: https://raw.githubusercontent.com/owkin/PyDESeq2/main/datasets/synthetic/; 151: https://pydeseq2.readthedocs.io/en/stable/api/docstrings/pydeseq2.dds.DeseqDataSet.html; 152: https://pydeseq2.readthedocs.io/en/stable/api/docstrings/pydeseq2.ds.DeseqStats.html; 153: https://pydeseq2.readthedocs.io/en/stable/usage/requirements.html; 154: https://github.com/scverse/PyDESeq2/blob/v0.5.4/pydeseq2/dds.py; 155: https://github.com/scverse/PyDESeq2/blob/v0.5.4/pydeseq2/ds.py; 156: https://github.com/scverse/PyDESeq2/blob/v0.5.4/pydeseq2/utils.py; 157: https://github.com/scverse/PyDESeq2/blob/v0.5.4/pydeseq2/preprocessing.py
- [references/core_workflow_steps.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/pydeseq2/references/core_workflow_steps.md):
  - hosts: 72: pydeseq2.readthedocs.io
  - urls: 72: https://pydeseq2.readthedocs.io/en/stable/auto_examples/plot_minimal_pydeseq2_pipeline.html
- [references/workflow_guide.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/pydeseq2/references/workflow_guide.md):
  - hosts: 181: github.com; 182: github.com; 183: pydeseq2.readthedocs.io; 184: bioconductor.org
  - urls: 181: https://github.com/scverse/PyDESeq2/blob/v0.5.4/pydeseq2/preprocessing.py; 182: https://github.com/scverse/PyDESeq2/blob/v0.5.4/pydeseq2/dds.py; 183: https://pydeseq2.readthedocs.io/en/stable/auto_examples/plot_step_by_step.html; 184: https://bioconductor.org/packages/release/bioc/vignettes/DESeq2/inst/doc/DESeq2.html
- [scripts/run_deseq2_analysis.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/pydeseq2/scripts/run_deseq2_analysis.py):
  - install: 34: uv pip install

### pylabrobot

- [SKILL.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/pylabrobot/SKILL.md):
  - hosts: 66: pypi.org; 194: localhost; 219: localhost; 223: pypi.org; 224: docs.pylabrobot.org; 225: github.com; 237: doi.org; 239: arxiv.org; 241: arxiv.org; 242: export.arxiv.org
  - install: 96: uv pip install
  - shell: 94: \`\`\`bash; 110: \`\`\`bash
  - urls: 66: https://pypi.org/project/PyLabRobot/0.2.2/#files; 223: https://pypi.org/project/PyLabRobot/0.2.2/#files; 224: https://docs.pylabrobot.org/stable/; 225: https://github.com/PyLabRobot/pylabrobot; 237: https://doi.org/10.48550/arXiv.2609.00065; 239: https://arxiv.org/abs/2609.00065; 241: https://arxiv.org/abs/2609.00065; 242: http://export.arxiv.org/api/query?id_list=2609.00065
- [assets/protocol-manifest.schema.json](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/pylabrobot/assets/protocol-manifest.schema.json):
  - hosts: 2: json-schema.org
  - urls: 2: https://json-schema.org/draft/2020-12/schema
- [references/analytical-equipment.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/pylabrobot/references/analytical-equipment.md):
  - hosts: 187: pypi.org; 189: docs.pylabrobot.org
  - shell: 70: \`\`\`bash
  - urls: 187: https://pypi.org/project/PyLabRobot/0.2.2/#files; 189: https://docs.pylabrobot.org/stable/user_guide/machines.html
- [references/hardware-backends.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/pylabrobot/references/hardware-backends.md):
  - hosts: 192: pypi.org; 193: docs.pylabrobot.org; 194: docs.opentrons.com
  - install: 120: uv pip install
  - shell: 83: \`\`\`bash; 118: \`\`\`bash
  - urls: 192: https://pypi.org/project/PyLabRobot/0.2.2/#files; 193: https://docs.pylabrobot.org/stable/user_guide/machines.html; 194: https://docs.opentrons.com/http/api_reference.html
- [references/liquid-handling.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/pylabrobot/references/liquid-handling.md):
  - hosts: 220: docs.pylabrobot.org; 222: docs.pylabrobot.org; 224: docs.pylabrobot.org; 226: docs.pylabrobot.org; 227: docs.pylabrobot.org; 228: pypi.org
  - shell: 204: \`\`\`bash
  - urls: 220: https://docs.pylabrobot.org/stable/user_guide/00_liquid-handling/hamilton-star/basic.html; 222: https://docs.pylabrobot.org/stable/api/pylabrobot.liquid_handling.html; 224: https://docs.pylabrobot.org/stable/user_guide/machine-agnostic-features/using-trackers.html; 226: https://docs.pylabrobot.org/stable/user_guide/00_liquid-handling/hamilton-star/hamilton-liquid-classes.html; 227: https://docs.pylabrobot.org/stable/user_guide/00_liquid-handling/hamilton-star/star_lld.html; 228: https://pypi.org/project/PyLabRobot/0.2.2/#files
- [references/material-handling.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/pylabrobot/references/material-handling.md):
  - hosts: 221: pypi.org; 222: docs.pylabrobot.org
  - shell: 210: \`\`\`bash
  - urls: 221: https://pypi.org/project/PyLabRobot/0.2.2/#files; 222: https://docs.pylabrobot.org/stable/user_guide/machines.html
- [references/resources.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/pylabrobot/references/resources.md):
  - hosts: 235: docs.pylabrobot.org; 236: docs.pylabrobot.org; 238: docs.pylabrobot.org; 240: docs.pylabrobot.org; 242: pypi.org
  - shell: 123: \`\`\`bash; 205: \`\`\`bash
  - urls: 235: https://docs.pylabrobot.org/stable/resources/introduction.html; 236: https://docs.pylabrobot.org/stable/api/pylabrobot.resources.html; 238: https://docs.pylabrobot.org/stable/user_guide/00_liquid-handling/hamilton-star/basic.html; 240: https://docs.pylabrobot.org/stable/user_guide/machine-agnostic-features/using-trackers.html; 242: https://pypi.org/project/PyLabRobot/0.2.2/#files
- [references/review.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/pylabrobot/references/review.md):
  - hosts: 9: pypi.org; 11: pypi.org; 16: api.github.com; 18: github.com; 22: docs.pylabrobot.org; 23: docs.pylabrobot.org; 24: docs.pylabrobot.org; 25: docs.pylabrobot.org; 70: docs.opentrons.com; 72: github.com; 73: github.com
  - urls: 9: https://pypi.org/pypi/pylabrobot/0.2.2/json; 11: https://pypi.org/project/PyLabRobot/0.2.2/#files; 16: https://api.github.com/repos/PyLabRobot/pylabrobot/tags?per_page=100; 18: https://github.com/PyLabRobot/pylabrobot/blob/main/CHANGELOG.md; 22: https://docs.pylabrobot.org/stable/user_guide/_getting-started/installation.html; 23: https://docs.pylabrobot.org/stable/api/pylabrobot.liquid_handling.html; 24: https://docs.pylabrobot.org/stable/user_guide/machines.html; 25: https://docs.pylabrobot.org/stable/user_guide/machine-agnostic-features/using-trackers.html; 70: https://docs.opentrons.com/http/api_reference.html; 72: https://github.com/Opentrons/opentrons/blob/edge/robot-server/robot_server/runs/action_models.py; 73: https://github.com/Opentrons/opentrons/blob/edge/robot-server/robot_server/runs/router/actions_router.py
- [references/visualization.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/pylabrobot/references/visualization.md):
  - hosts: 14: localhost; 58: 127.0.0.1; 79: localhost; 177: docs.pylabrobot.org; 179: docs.pylabrobot.org; 181: docs.pylabrobot.org; 183: docs.pylabrobot.org; 185: pypi.org; 186: pypi.org
  - shell: 125: \`\`\`bash; 162: \`\`\`bash
  - urls: 177: https://docs.pylabrobot.org/stable/user_guide/machine-agnostic-features/using-the-visualizer.html; 179: https://docs.pylabrobot.org/stable/contributor_guide/visualizer.html; 181: https://docs.pylabrobot.org/stable/user_guide/machine-agnostic-features/using-trackers.html; 183: https://docs.pylabrobot.org/stable/api/pylabrobot.liquid_handling.html; 185: https://pypi.org/project/PyLabRobot/0.2.2/#files; 186: https://pypi.org/project/PyLabRobot/0.2.2/#files
- [scripts/__init__.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/pylabrobot/scripts/__init__.py): no matches
- [scripts/_common.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/pylabrobot/scripts/_common.py): no matches
- [scripts/check_deck_geometry.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/pylabrobot/scripts/check_deck_geometry.py): no matches
- [scripts/generate_simulation_plan.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/pylabrobot/scripts/generate_simulation_plan.py): no matches
- [scripts/inspect_backends.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/pylabrobot/scripts/inspect_backends.py): no matches
- [scripts/plan_transfers.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/pylabrobot/scripts/plan_transfers.py): no matches
- [scripts/validate_manifest.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/pylabrobot/scripts/validate_manifest.py): no matches

### pysam

- [SKILL.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/pysam/SKILL.md):
  - hosts: 318: www.htslib.org; 358: doi.org; 360: arxiv.org; 362: arxiv.org; 363: export.arxiv.org
  - install: 34: uv pip install
  - shell: 33: \`\`\`bash; 65: \`\`\`bash
  - urls: 318: https://www.htslib.org/doc/samtools-quickcheck.html; 358: https://doi.org/10.48550/arXiv.2609.00065; 360: https://arxiv.org/abs/2609.00065; 362: https://arxiv.org/abs/2609.00065; 363: http://export.arxiv.org/api/query?id_list=2609.00065
- [references/alignment_files.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/pysam/references/alignment_files.md): no matches
- [references/api_reference.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/pysam/references/api_reference.md): no matches
- [references/common_workflows.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/pysam/references/common_workflows.md):
  - hosts: 266: header.info; 268: header.info; 282: record.info; 466: variants.header.info
  - shell: 22: \`\`\`bash; 32: \`\`\`bash; 327: \`\`\`bash
- [references/coordinates_and_indexing.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/pysam/references/coordinates_and_indexing.md): no matches
- [references/cram_and_performance.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/pysam/references/cram_and_performance.md):
  - hosts: 187: example.org; 189: example.org
  - urls: 187: https://example.org/data/sample.bam; 189: https://example.org/data/sample.bam.bai
- [references/migration_to_0_24.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/pysam/references/migration_to_0_24.md):
  - install: 17: uv pip install
  - shell: 16: \`\`\`bash
- [references/sequence_files.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/pysam/references/sequence_files.md): no matches
- [references/sources.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/pysam/references/sources.md):
  - hosts: 14: pypi.org; 16: pysam.readthedocs.io; 19: github.com; 21: github.com; 40: pysam.readthedocs.io; 41: pysam.readthedocs.io; 42: pysam.readthedocs.io; 43: pysam.readthedocs.io; 44: pysam.readthedocs.io; 45: pysam.readthedocs.io; 46: pysam.readthedocs.io; 63: www.htslib.org; 64: www.htslib.org; 65: www.htslib.org; 66: www.htslib.org; 67: www.htslib.org; 68: www.htslib.org; 76: pysam.readthedocs.io; 78: www.htslib.org; 80: www.htslib.org; 89: samtools.github.io; 90: samtools.github.io; 91: samtools.github.io; 92: samtools.github.io; 93: samtools.github.io; 94: samtools.github.io; 95: samtools.github.io; 96: samtools.github.io; 97: samtools.github.io; 108: github.com; 109: github.com; 110: github.com; 111: github.com; 112: github.com; 113: github.com; 135: example.org
  - urls: 14: https://pypi.org/project/pysam/; 16: https://pysam.readthedocs.io/en/stable/release.html; 19: https://github.com/pysam-developers/pysam; 21: https://github.com/pysam-developers/pysam/tree/v0.24.1; 40: https://pysam.readthedocs.io/en/stable/index.html; 41: https://pysam.readthedocs.io/en/stable/installation.html; 42: https://pysam.readthedocs.io/en/stable/usage.html; 43: https://pysam.readthedocs.io/en/stable/api.html; 44: https://pysam.readthedocs.io/en/stable/faq.html; 45: https://pysam.readthedocs.io/en/stable/release.html; 46: https://pysam.readthedocs.io/en/stable/glossary.html; 63: https://www.htslib.org/doc/1.24/samtools.html; 64: https://www.htslib.org/doc/1.24/bcftools.html; 65: https://www.htslib.org/doc/1.24/tabix.html; 66: https://www.htslib.org/doc/1.24/bgzip.html; 67: https://www.htslib.org/doc/1.24/faidx.html; 68: https://www.htslib.org/doc/; 76: https://pysam.readthedocs.io/en/stable/release.html#release-0-24-0; 78: https://www.htslib.org/doc/1.24/samtools.html; 80: https://www.htslib.org/workflow/cram.html; 89: https://samtools.github.io/hts-specs/; 90: https://samtools.github.io/hts-specs/SAMv1.pdf; 91: https://samtools.github.io/hts-specs/SAMtags.pdf; 92: https://samtools.github.io/hts-specs/CRAMv3.pdf; 93: https://samtools.github.io/hts-specs/VCFv4.5.pdf; 94: https://samtools.github.io/hts-specs/BCFv2_qref.pdf; 95: https://samtools.github.io/hts-specs/tabix.pdf; 96: https://samtools.github.io/hts-specs/CSIv1.pdf; 97: https://samtools.github.io/hts-specs/BEDv1.pdf; 108: https://github.com/pysam-developers/pysam/blob/v0.24.1/pysam/libcalignmentfile.pyx; 109: https://github.com/pysam-developers/pysam/blob/v0.24.1/pysam/libcalignedsegment.pyx; 110: https://github.com/pysam-developers/pysam/blob/v0.24.1/pysam/libcbcf.pyx; 111: https://github.com/pysam-developers/pysam/blob/v0.24.1/pysam/libcfaidx.pyx; 112: https://github.com/pysam-developers/pysam/blob/v0.24.1/pysam/libctabix.pyx; 113: https://github.com/pysam-developers/pysam/blob/v0.24.1/pysam/utils.py
- [references/variant_files.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/pysam/references/variant_files.md):
  - hosts: 99: header.info; 108: header.info; 143: record.info; 144: record.info; 277: record.info; 290: header.info; 314: record.info; 335: record.info; 344: record.info
- [scripts/alignment_qc.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/pysam/scripts/alignment_qc.py):
  - home_paths: 75: expanduser(; 303: expanduser(; 314: expanduser(
- [scripts/filter_alignments.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/pysam/scripts/filter_alignments.py):
  - home_paths: 119: expanduser(; 214: expanduser(; 216: expanduser(; 360: expanduser(
- [scripts/inspect_hts.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/pysam/scripts/inspect_hts.py):
  - home_paths: 135: expanduser(; 463: expanduser(; 474: expanduser(
  - hosts: 283: header.info
- [scripts/variant_summary.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/pysam/scripts/variant_summary.py):
  - home_paths: 82: expanduser(; 343: expanduser(; 354: expanduser(

### pytdc

- [SKILL.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/pytdc/SKILL.md):
  - hosts: 32: tdc.readthedocs.io; 69: pypi.org; 255: tdcommons.ai; 318: doi.org; 320: arxiv.org; 322: arxiv.org; 323: export.arxiv.org
  - install: 47: uv pip install; 49: uv pip install
  - outside_writes: 95: &gt;/
  - shell: 45: \`\`\`bash; 62: \`\`\`bash; 114: \`\`\`bash; 141: \`\`\`bash; 150: \`\`\`bash; 266: \`\`\`bash; 273: \`\`\`bash
  - urls: 69: https://pypi.org/project/pytdc/; 255: https://tdcommons.ai/benchmark/overview/; 318: https://doi.org/10.48550/arXiv.2609.00065; 320: https://arxiv.org/abs/2609.00065; 322: https://arxiv.org/abs/2609.00065; 323: http://export.arxiv.org/api/query?id_list=2609.00065
- [references/datasets.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/pytdc/references/datasets.md):
  - hosts: 110: doi.org; 114: dataverse.harvard.edu; 240: tdcommons.ai
  - shell: 12: \`\`\`bash; 150: \`\`\`bash
  - urls: 110: https://doi.org/10.7910/DVN/21LKWG; 114: https://dataverse.harvard.edu/api/access/datafile/{numeric_file_id; 240: https://tdcommons.ai/single_pred_tasks/adme
- [references/oracles.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/pytdc/references/oracles.md):
  - shell: 21: \`\`\`bash; 149: \`\`\`bash; 160: \`\`\`bash; 169: \`\`\`bash; 215: \`\`\`bash; 221: \`\`\`bash; 232: \`\`\`bash
- [references/sources.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/pytdc/references/sources.md):
  - hosts: 13: pypi.org; 21: pypi.org; 24: github.com; 27: github.com; 31: pypi.org; 33: pypi.org; 36: setuptools.pypa.io; 50: github.com; 53: github.com; 55: github.com; 56: github.com; 57: github.com; 58: github.com; 59: github.com; 60: github.com; 61: github.com; 62: github.com; 63: github.com; 64: github.com; 65: github.com; 66: github.com; 67: github.com; 68: github.com; 69: github.com; 76: tdcommons.ai; 78: tdcommons.ai; 81: tdcommons.ai; 83: tdcommons.ai; 86: tdcommons.ai; 88: tdcommons.ai; 90: tdcommons.ai; 92: tdcommons.ai; 95: tdcommons.ai; 97: tdcommons.ai; 99: tdc.readthedocs.io; 102: doi.org; 105: guides.dataverse.org; 108: github.com; 111: github.com; 123: doi.org
  - urls: 13: https://pypi.org/project/pytdc/; 21: https://pypi.org/pypi/PyTDC/1.1.15/json; 24: https://github.com/mims-harvard/TDC/blob/main/setup.py; 27: https://github.com/mims-harvard/TDC/blob/main/requirements.txt; 31: https://pypi.org/pypi/cellxgene-census/1.15.0/json; 33: https://pypi.org/pypi/rdkit/2023.9.6/json; 36: https://setuptools.pypa.io/en/stable/history.html; 50: https://github.com/mims-harvard/TDC/blob/main/tdc/metadata.py; 53: https://github.com/mims-harvard/TDC/blob/main/tdc/__init__.py; 55: https://github.com/mims-harvard/TDC/blob/main/tdc/single_pred/__init__.py; 56: https://github.com/mims-harvard/TDC/blob/main/tdc/multi_pred/__init__.py; 57: https://github.com/mims-harvard/TDC/blob/main/tdc/generation/__init__.py; 58: https://github.com/mims-harvard/TDC/blob/main/tdc/base_dataset.py; 59: https://github.com/mims-harvard/TDC/blob/main/tdc/single_pred/single_pred_dataset.py; 60: https://github.com/mims-harvard/TDC/blob/main/tdc/multi_pred/bi_pred_dataset.py; 61: https://github.com/mims-harvard/TDC/blob/main/tdc/multi_pred/multi_pred_dataset.py; 62: https://github.com/mims-harvard/TDC/blob/main/tdc/generation/generation_dataset.py; 63: https://github.com/mims-harvard/TDC/blob/main/tdc/utils/split.py; 64: https://github.com/mims-harvard/TDC/blob/main/tdc/evaluator.py; 65: https://github.com/mims-harvard/TDC/blob/main/tdc/oracles.py; 66: https://github.com/mims-harvard/TDC/blob/main/tdc/utils/load.py; 67: https://github.com/mims-harvard/TDC/blob/main/tdc/utils/retrieve.py; 68: https://github.com/mims-harvard/TDC/blob/main/tdc/benchmark_group/base_group.py; 69: https://github.com/mims-harvard/TDC/blob/main/tdc/benchmark_deprecated.py; 76: https://tdcommons.ai/start/; 78: https://tdcommons.ai/functions/data_split/; 81: https://tdcommons.ai/functions/data_evaluation/; 83: https://tdcommons.ai/benchmark/overview/; 86: https://tdcommons.ai/benchmark/admet_group/overview; 88: https://tdcommons.ai/functions/oracles/; 90: https://tdcommons.ai/generation_tasks/molgen; 92: https://tdcommons.ai/single_pred_tasks/adme; 95: https://tdcommons.ai/multi_pred_tasks/dti/; 97: https://tdcommons.ai/multi_pred_tasks/trialoutcome/; 99: https://tdc.readthedocs.io/; 102: https://doi.org/10.7910/DVN/21LKWG; 105: https://guides.dataverse.org/en/latest/api/dataaccess.html; 108: https://github.com/mims-harvard/TDC/blob/main/tdc/resource/primekg.py; 111: https://github.com/mims-harvard/TDC/blob/main/tdc/chem_utils/evaluator.py; 118: https://datasets-benchmarks-proceedings.neurips.cc/paper_files/paper/2021/hash/4c56ff4ce4aaf9573aa5dff913df997a-Abstract-round1.html; 123: https://doi.org/10.1038/s41589-022-01131-2
- [references/utilities.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/pytdc/references/utilities.md):
  - shell: 178: \`\`\`bash; 365: \`\`\`bash
- [scripts/_common.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/pytdc/scripts/_common.py):
  - install: 125: uv pip install
- [scripts/benchmark_evaluation.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/pytdc/scripts/benchmark_evaluation.py): no matches
- [scripts/cache_audit.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/pytdc/scripts/cache_audit.py): no matches
- [scripts/discover_metadata.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/pytdc/scripts/discover_metadata.py): no matches
- [scripts/load_and_split_data.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/pytdc/scripts/load_and_split_data.py): no matches
- [scripts/molecular_generation.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/pytdc/scripts/molecular_generation.py): no matches

### rdkit

- [SKILL.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/rdkit/SKILL.md):
  - hosts: 133: doi.org; 135: arxiv.org; 137: arxiv.org; 138: export.arxiv.org
  - install: 27: uv pip install
  - shell: 26: \`\`\`bash; 32: \`\`\`bash
  - urls: 133: https://doi.org/10.48550/arXiv.2609.00065; 135: https://arxiv.org/abs/2609.00065; 137: https://arxiv.org/abs/2609.00065; 138: http://export.arxiv.org/api/query?id_list=2609.00065
- [references/api_reference.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/rdkit/references/api_reference.md):
  - install: 435: uv pip install
  - shell: 433: \`\`\`bash
- [references/core_capabilities.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/rdkit/references/core_capabilities.md): no matches
- [references/descriptors_reference.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/rdkit/references/descriptors_reference.md): no matches
- [references/review.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/rdkit/references/review.md):
  - hosts: 10: github.com; 11: pypi.org; 12: www.rdkit.org; 13: www.rdkit.org; 15: www.rdkit.org; 17: github.com; 21: www.rdkit.org; 22: www.rdkit.org; 23: www.rdkit.org; 24: www.rdkit.org; 25: www.rdkit.org; 26: www.rdkit.org; 27: www.rdkit.org; 28: www.rdkit.org; 29: www.rdkit.org; 30: www.rdkit.org; 31: github.com; 32: www.rdkit.org; 33: github.com; 36: www.rdkit.org; 37: github.com; 38: www.rdkit.org; 39: www.rdkit.org; 40: www.rdkit.org; 41: www.rdkit.org; 42: www.rdkit.org
  - urls: 10: https://github.com/rdkit/rdkit/releases/tag/Release_2026_03_6; 11: https://pypi.org/pypi/rdkit/json; 12: https://www.rdkit.org/docs/Install.html; 13: https://www.rdkit.org/docs/GettingStartedInPython.html; 15: https://www.rdkit.org/docs/RDKit_Book.html; 17: https://github.com/rdkit/rdkit/releases/tag/Release_2026_03_1; 21: https://www.rdkit.org/docs/source/rdkit.Chem.rdmolfiles.html; 22: https://www.rdkit.org/docs/source/rdkit.Chem.rdmolops.html; 23: https://www.rdkit.org/docs/source/rdkit.Chem.rdchem.html; 24: https://www.rdkit.org/docs/source/rdkit.Chem.rdFingerprintGenerator.html; 25: https://www.rdkit.org/docs/source/rdkit.Chem.AtomPairs.Pairs.html; 26: https://www.rdkit.org/docs/source/rdkit.Chem.AtomPairs.Torsions.html; 27: https://www.rdkit.org/docs/source/rdkit.DataStructs.html; 28: https://www.rdkit.org/docs/source/rdkit.ML.Cluster.Butina.html; 29: https://www.rdkit.org/docs/source/rdkit.Chem.Descriptors.html; 30: https://www.rdkit.org/docs/source/rdkit.Chem.rdMolDescriptors.html; 31: https://github.com/rdkit/rdkit/blob/Release_2026_03_6/rdkit/Chem/Lipinski.py; 32: https://www.rdkit.org/docs/source/rdkit.Chem.MolStandardize.rdMolStandardize.html; 33: https://github.com/rdkit/rdkit/blob/Release_2026_03_6/Code/GraphMol/MolStandardize/MolStandardize.cpp; 36: https://www.rdkit.org/docs/source/rdkit.Chem.rdDistGeom.html; 37: https://github.com/rdkit/rdkit/blob/Release_2026_03_6/Code/GraphMol/ForceFieldHelpers/Wrap/rdForceFields.cpp; 38: https://www.rdkit.org/docs/source/rdkit.Chem.Draw.html; 39: https://www.rdkit.org/docs/source/rdkit.Chem.rdChemReactions.html; 40: https://www.rdkit.org/docs/source/rdkit.Chem.rdMolHash.html; 41: https://www.rdkit.org/docs/source/rdkit.Chem.Scaffolds.MurckoScaffold.html; 42: https://www.rdkit.org/docs/source/rdkit.Chem.FilterCatalog.html
- [references/smarts_patterns.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/rdkit/references/smarts_patterns.md): no matches
- [references/workflows_and_best_practices.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/rdkit/references/workflows_and_best_practices.md):
  - dynamic_code: 116: base64.b64decode(
- [scripts/_common.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/rdkit/scripts/_common.py): no matches
- [scripts/molecular_properties.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/rdkit/scripts/molecular_properties.py):
  - install: 20: uv pip install
- [scripts/similarity_search.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/rdkit/scripts/similarity_search.py):
  - install: 23: uv pip install
- [scripts/substructure_filter.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/rdkit/scripts/substructure_filter.py):
  - install: 20: uv pip install

### rowan

- [SKILL.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/rowan/SKILL.md):
  - env: 5: ROWAN_API_KEY; 13: ROWAN_API_KEY; 15: ROWAN_API_KEY; 52: ROWAN_API_KEY; 85: ROWAN_API_KEY
  - hosts: 65: pypi.org; 66: docs.rowansci.com; 349: www.rcsb.org
  - install: 47: uv pip install; 74: uv pip install
  - shell: 46: \`\`\`bash; 73: \`\`\`bash; 84: \`\`\`bash
  - urls: 65: https://pypi.org/project/rowan-python/3.2.0/; 66: https://docs.rowansci.com/api/python/v3/; 349: https://www.rcsb.org/structure/1M17
- [references/access_and_pricing.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/rowan/references/access_and_pricing.md):
  - hosts: 3: rowansci.com
  - urls: 3: https://rowansci.com/pricing
- [references/batch_and_webhooks.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/rowan/references/batch_and_webhooks.md):
  - env: 24: ROWAN_API_KEY; 125: ROWAN_WEBHOOK_SECRET
  - environment_access: 125: os.environ
  - hosts: 5: docs.rowansci.com; 6: docs.rowansci.com; 94: example.org; 160: api.rowansci.com
  - urls: 5: https://docs.rowansci.com/api/python/v3/api/workflow/; 6: https://docs.rowansci.com/api/python/v3/api/webhooks/; 94: https://example.org/rowan_callback; 160: https://api.rowansci.com
- [references/end_to_end_example.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/rowan/references/end_to_end_example.md):
  - env: 8: ROWAN_API_KEY
- [references/troubleshooting.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/rowan/references/troubleshooting.md):
  - env: 59: ROWAN_API_KEY; 68: ROWAN_API_KEY; 73: ROWAN_API_KEY; 75: ROWAN_API_KEY
  - environment_access: 73: os.environ.get
- [references/workflow_catalog.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/rowan/references/workflow_catalog.md):
  - hosts: 5: pypi.org; 6: docs.rowansci.com
  - urls: 5: https://pypi.org/project/rowan-python/3.2.0/; 6: https://docs.rowansci.com/api/python/v3/

### scanpy

- [SKILL.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/scanpy/SKILL.md):
  - hosts: 29: docs.dask.org; 35: scanpy.scverse.org; 35: rapids-singlecell.readthedocs.io; 328: scanpy.scverse.org; 329: scanpy.scverse.org; 330: scanpy.scverse.org; 331: scverse.org; 332: www.bioconductor.org; 332: mojaveazure.github.io; 353: doi.org; 355: arxiv.org; 357: arxiv.org; 358: export.arxiv.org
  - install: 24: uv pip install; 27: uv pip install; 32: uv pip install
  - shell: 23: \`\`\`bash; 31: \`\`\`bash; 115: \`\`\`bash; 127: \`\`\`bash; 171: \`\`\`bash; 312: \`\`\`bash
  - urls: 29: https://docs.dask.org/; 35: https://scanpy.scverse.org/en/stable/tutorials/experimental/dask.html; 35: https://rapids-singlecell.readthedocs.io/; 328: https://scanpy.scverse.org/en/stable/; 329: https://scanpy.scverse.org/en/stable/tutorials/index.html; 330: https://scanpy.scverse.org/en/stable/release-notes/index.html; 331: https://scverse.org/; 332: https://www.bioconductor.org/packages/release/bioc/html/zellkonverter.html; 332: https://mojaveazure.github.io/seurat-disk/; 353: https://doi.org/10.48550/arXiv.2609.00065; 355: https://arxiv.org/abs/2609.00065; 357: https://arxiv.org/abs/2609.00065; 358: http://export.arxiv.org/api/query?id_list=2609.00065
- [assets/analysis_template.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/scanpy/assets/analysis_template.py): no matches
- [assets/celltype_mapping.json](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/scanpy/assets/celltype_mapping.json): no matches
- [assets/gene_signatures.json](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/scanpy/assets/gene_signatures.json): no matches
- [assets/pipeline_config.json](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/scanpy/assets/pipeline_config.json): no matches
- [references/analysis_workflow.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/scanpy/references/analysis_workflow.md):
  - shell: 47: \`\`\`bash
- [references/api_reference.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/scanpy/references/api_reference.md): no matches
- [references/plotting_guide.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/scanpy/references/plotting_guide.md): no matches
- [references/r_interop.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/scanpy/references/r_interop.md):
  - env: 117: PWD
  - hosts: 64: mac.R-project.org; 123: cloud.r-project.org; 129: cloud.r-project.org; 135: cloud.r-project.org; 174: cloud.r-project.org; 279: scipy.io; 301: github.com; 303: theislab.github.io; 303: satijalab.github.io; 303: satijalab.org; 304: mojaveazure.github.io; 306: www.r-project.org; 306: cran.r-project.org; 307: www.bioconductor.org; 307: cran.r-project.org; 308: www.bioconductor.org; 308: github.com; 309: mojaveazure.github.io; 309: github.com; 310: github.com
  - install: 55: brew install
  - outside_writes: 21: &gt;/; 23: &gt;/
  - shell: 20: \`\`\`bash; 42: \`\`\`bash; 54: \`\`\`bash; 60: \`\`\`bash; 70: \`\`\`bash; 81: \`\`\`bash; 91: \`\`\`bash; 115: \`\`\`bash; 122: \`\`\`bash; 128: \`\`\`bash; 134: \`\`\`bash; 144: \`\`\`bash; 150: \`\`\`bash; 226: \`\`\`bash; 232: \`\`\`bash
  - urls: 64: https://mac.R-project.org/tools/; 123: https://cloud.r-project.org; 129: https://cloud.r-project.org; 135: https://cloud.r-project.org; 174: https://cloud.r-project.org; 300: https://formulae.brew.sh/cask/r-app; 301: https://github.com/microsoft/winget-pkgs/tree/master/manifests/r/RProject; 303: https://theislab.github.io/zellkonverter/reference/writeH5AD.html; 303: https://satijalab.github.io/seurat-object/reference/UpdateSeuratObject.html; 303: https://satijalab.github.io/seurat-object/reference/SplitLayers.html; 303: https://satijalab.org/seurat/reference/as.singlecellexperiment; 304: https://mojaveazure.github.io/seurat-disk/reference/Convert.html; 306: https://www.r-project.org/; 306: https://cran.r-project.org/bin/macosx; 306: https://cran.r-project.org/bin/windows/base/rw-FAQ.html; 307: https://www.bioconductor.org/install/; 307: https://cran.r-project.org/web/packages/BiocManager/vignettes/BiocManager.html; 308: https://www.bioconductor.org/packages/release/bioc/html/zellkonverter.html; 308: https://github.com/theislab/zellkonverter; 309: https://mojaveazure.github.io/seurat-disk/; 309: https://github.com/mojaveazure/seurat-disk; 310: https://github.com/cellgeni/sceasy
- [references/standard_workflow.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/scanpy/references/standard_workflow.md): no matches
- [references/upstream-review.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/scanpy/references/upstream-review.md):
  - hosts: 71: scanpy.readthedocs.io; 73: scanpy.readthedocs.io; 74: scanpy.readthedocs.io; 75: scanpy.readthedocs.io; 76: scanpy.readthedocs.io; 77: scanpy.readthedocs.io; 78: scanpy.readthedocs.io; 79: scanpy.readthedocs.io; 80: anndata.readthedocs.io; 81: anndata.readthedocs.io; 81: anndata.io; 82: github.com; 83: scanpy.readthedocs.io; 85: github.com; 89: scanpy.readthedocs.io; 98: scanpy.readthedocs.io; 101: scanpy.readthedocs.io
  - urls: 71: https://scanpy.readthedocs.io/en/stable/release-notes/index.html; 73: https://scanpy.readthedocs.io/en/stable/generated/scanpy.pp.highly_variable_genes.html; 74: https://scanpy.readthedocs.io/en/stable/generated/scanpy.pp.pca.html; 75: https://scanpy.readthedocs.io/en/stable/generated/scanpy.pp.neighbors.html; 76: https://scanpy.readthedocs.io/en/stable/generated/scanpy.tl.leiden.html; 77: https://scanpy.readthedocs.io/en/stable/generated/scanpy.tl.rank_genes_groups.html; 78: https://scanpy.readthedocs.io/en/stable/generated/scanpy.get.aggregate.html; 79: https://scanpy.readthedocs.io/en/stable/generated/scanpy.tl.score_genes.html; 80: https://anndata.readthedocs.io/en/stable/generated/anndata.AnnData.raw.html; 81: https://anndata.readthedocs.io/en/stable/generated/anndata.io.read_h5ad.html; 82: https://github.com/scverse/anndata/tree/0.13.4; 83: https://scanpy.readthedocs.io/en/stable/generated/scanpy.external.pp.harmony_integrate.html; 85: https://github.com/slowkow/harmonypy; 89: https://scanpy.readthedocs.io/en/stable/generated/scanpy.external.pp.bbknn.html; 98: https://scanpy.readthedocs.io/en/stable/generated/scanpy.tl.dpt.html; 101: https://scanpy.readthedocs.io/en/stable/generated/scanpy.tl.ingest.html
- [scripts/_common.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/scanpy/scripts/_common.py):
  - install: 32: uv pip install
- [scripts/annotate.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/scanpy/scripts/annotate.py): no matches
- [scripts/batch_correct.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/scanpy/scripts/batch_correct.py):
  - install: 7: uv pip install; 10: uv pip install; 49: uv pip install; 61: uv pip install
- [scripts/cluster.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/scanpy/scripts/cluster.py): no matches
- [scripts/convert.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/scanpy/scripts/convert.py): no matches
- [scripts/find_markers.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/scanpy/scripts/find_markers.py): no matches
- [scripts/inspect_data.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/scanpy/scripts/inspect_data.py): no matches
- [scripts/plot.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/scanpy/scripts/plot.py): no matches
- [scripts/preprocess.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/scanpy/scripts/preprocess.py): no matches
- [scripts/pseudobulk.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/scanpy/scripts/pseudobulk.py): no matches
- [scripts/qc_analysis.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/scanpy/scripts/qc_analysis.py): no matches
- [scripts/reduce_dimensions.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/scanpy/scripts/reduce_dimensions.py): no matches
- [scripts/run_pipeline.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/scanpy/scripts/run_pipeline.py): no matches
- [scripts/score_genes.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/scanpy/scripts/score_genes.py): no matches
- [scripts/subset.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/scanpy/scripts/subset.py): no matches

### scvi-tools

- [SKILL.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/scvi-tools/SKILL.md):
  - hosts: 59: scviva-tools.readthedocs.io; 175: github.com; 176: github.com; 177: docs.scvi-tools.org; 187: doi.org; 189: arxiv.org; 191: arxiv.org; 192: export.arxiv.org
  - install: 161: uv pip install
  - shell: 159: \`\`\`bash
  - urls: 59: https://scviva-tools.readthedocs.io/en/latest/; 175: https://github.com/scverse/scvi-tools/blob/1.5.1/CHANGELOG.md; 176: https://github.com/scverse/scvi-tools/blob/1.5.1/pyproject.toml; 177: https://docs.scvi-tools.org/en/stable/api/index.html; 187: https://doi.org/10.48550/arXiv.2609.00065; 189: https://arxiv.org/abs/2609.00065; 191: https://arxiv.org/abs/2609.00065; 192: http://export.arxiv.org/api/query?id_list=2609.00065
- [references/differential-expression.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/scvi-tools/references/differential-expression.md):
  - hosts: 136: github.com; 137: github.com; 138: github.com; 139: docs.scvi-tools.org; 140: github.com; 141: github.com
  - urls: 136: https://github.com/scverse/scvi-tools/blob/1.5.1/src/scvi/model/base/_rnamixin.py; 137: https://github.com/scverse/scvi-tools/blob/1.5.1/src/scvi/model/base/_differential.py; 138: https://github.com/scverse/scvi-tools/blob/1.5.1/src/scvi/model/base/_de_core.py; 139: https://docs.scvi-tools.org/en/stable/api/reference/scvi.model.TOTALVI.html; 140: https://github.com/scverse/scvi-tools/blob/1.5.1/src/scvi/model/_peakvi.py; 141: https://github.com/scverse/scvi-tools/blob/1.5.1/src/scvi/model/base/_vaemixin.py
- [references/models-atac-seq.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/scvi-tools/references/models-atac-seq.md):
  - hosts: 108: github.com; 109: github.com; 110: github.com; 111: github.com
  - urls: 108: https://github.com/scverse/scvi-tools/blob/1.5.1/src/scvi/model/_peakvi.py; 109: https://github.com/scverse/scvi-tools/blob/1.5.1/src/scvi/external/poissonvi/_model.py; 110: https://github.com/scverse/scvi-tools/blob/1.5.1/src/scvi/external/scbasset/_model.py; 111: https://github.com/scverse/scvi-tools/blob/1.5.1/src/scvi/data/_preprocessing.py
- [references/models-multimodal.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/scvi-tools/references/models-multimodal.md):
  - hosts: 163: github.com; 164: github.com; 165: github.com; 166: github.com; 167: github.com; 168: github.com; 169: docs.scvi-tools.org
  - urls: 163: https://github.com/scverse/scvi-tools/blob/1.5.1/src/scvi/model/_totalvi.py; 164: https://github.com/scverse/scvi-tools/blob/1.5.1/src/scvi/external/totalanvi/_model.py; 165: https://github.com/scverse/scvi-tools/blob/1.5.1/src/scvi/model/_multivi.py; 166: https://github.com/scverse/scvi-tools/blob/1.5.1/src/scvi/data/_preprocessing.py; 167: https://github.com/scverse/scvi-tools/blob/1.5.1/src/scvi/external/mrvi/_model.py; 168: https://github.com/scverse/scvi-tools/blob/1.5.1/src/scvi/external/diagvi/_model.py; 169: https://docs.scvi-tools.org/en/stable/user_guide/models/diagvi.html
- [references/models-scrna-seq.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/scvi-tools/references/models-scrna-seq.md):
  - hosts: 169: docs.scvi-tools.org; 170: docs.scvi-tools.org; 171: github.com; 172: github.com; 173: github.com; 174: github.com; 175: github.com; 176: github.com; 177: github.com; 178: github.com
  - urls: 169: https://docs.scvi-tools.org/en/stable/api/reference/scvi.model.SCVI.html; 170: https://docs.scvi-tools.org/en/stable/api/reference/scvi.model.SCANVI.html; 171: https://github.com/scverse/scvi-tools/blob/1.5.1/src/scvi/model/base/_training_mixin.py; 172: https://github.com/scverse/scvi-tools/blob/1.5.1/src/scvi/model/_autozi.py; 173: https://github.com/scverse/scvi-tools/blob/1.5.1/src/scvi/external/velovi/_model.py; 174: https://github.com/scverse/scvi-tools/blob/1.5.1/src/scvi/external/contrastivevi/_model.py; 175: https://github.com/scverse/scvi-tools/blob/1.5.1/src/scvi/external/cellassign/_model.py; 176: https://github.com/scverse/scvi-tools/blob/1.5.1/src/scvi/external/solo/_model.py; 177: https://github.com/scverse/scvi-tools/blob/1.5.1/src/scvi/model/_linear_scvi.py; 178: https://github.com/scverse/scvi-tools/blob/1.5.1/src/scvi/model/_amortizedlda.py
- [references/models-spatial.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/scvi-tools/references/models-spatial.md):
  - hosts: 4: scviva-tools.readthedocs.io; 190: github.com; 191: github.com; 192: github.com; 193: github.com; 194: github.com; 195: github.com; 196: github.com
  - urls: 4: https://scviva-tools.readthedocs.io/en/latest/; 190: https://github.com/scverse/scvi-tools/blob/1.5.1/docs/user_guide/models/destvi.md; 191: https://github.com/scverse/scvi-tools/blob/1.5.1/src/scvi/model/_destvi.py; 192: https://github.com/scverse/scvi-tools/blob/1.5.1/src/scvi/external/stereoscope/_model.py; 193: https://github.com/scverse/scvi-tools/blob/1.5.1/src/scvi/external/tangram/_model.py; 194: https://github.com/scverse/scvi-tools/blob/1.5.1/src/scvi/external/gimvi/_model.py; 195: https://github.com/scverse/scvi-tools/blob/1.5.1/src/scvi/external/scviva/_model.py; 196: https://github.com/scverse/scvi-tools/blob/1.5.1/src/scvi/external/resolvi/_model.py
- [references/models-specialized.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/scvi-tools/references/models-specialized.md):
  - hosts: 131: github.com; 132: github.com; 133: github.com; 134: github.com; 135: github.com; 136: github.com; 137: github.com
  - urls: 131: https://github.com/scverse/scvi-tools/blob/1.5.1/src/scvi/external/methylvi/_methylvi_model.py; 132: https://github.com/scverse/scvi-tools/blob/1.5.1/src/scvi/external/methylvi/_methylanvi_model.py; 133: https://github.com/scverse/scvi-tools/blob/1.5.1/src/scvi/external/methylvi/_base_components.py; 134: https://github.com/scverse/scvi-tools/blob/1.5.1/src/scvi/external/cytovi/_model.py; 135: https://github.com/scverse/scvi-tools/blob/1.5.1/docs/user_guide/models/cytovi.md; 136: https://github.com/scverse/scvi-tools/blob/1.5.1/docs/user_guide/models/sysvi.md; 137: https://github.com/scverse/scvi-tools/blob/1.5.1/src/scvi/external/decipher/_model.py
- [references/theoretical-foundations.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/scvi-tools/references/theoretical-foundations.md):
  - hosts: 86: docs.scvi-tools.org; 87: docs.scvi-tools.org; 88: docs.scvi-tools.org; 89: github.com; 90: docs.scvi-tools.org; 91: docs.scvi-tools.org; 92: github.com
  - urls: 86: https://docs.scvi-tools.org/en/stable/user_guide/background/variational_inference.html; 87: https://docs.scvi-tools.org/en/stable/user_guide/models/scvi.html; 88: https://docs.scvi-tools.org/en/stable/user_guide/models/autozi.html; 89: https://github.com/scverse/scvi-tools/blob/1.5.1/docs/user_guide/models/sysvi.md; 90: https://docs.scvi-tools.org/en/stable/user_guide/models/mrvi.html; 91: https://docs.scvi-tools.org/en/stable/user_guide/models/destvi.html; 92: https://github.com/scverse/scvi-tools/blob/1.5.1/src/scvi/model/base/_archesmixin.py
- [references/workflows.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/scvi-tools/references/workflows.md):
  - hosts: 183: github.com; 184: github.com; 185: github.com; 186: github.com; 187: docs.scvi-tools.org; 188: docs.scvi-tools.org
  - urls: 183: https://github.com/scverse/scvi-tools/blob/1.5.1/src/scvi/model/base/_training_mixin.py; 184: https://github.com/scverse/scvi-tools/blob/1.5.1/src/scvi/train/_metrics.py; 185: https://github.com/scverse/scvi-tools/blob/1.5.1/src/scvi/model/base/_base_model.py; 186: https://github.com/scverse/scvi-tools/blob/1.5.1/src/scvi/model/base/_archesmixin.py; 187: https://docs.scvi-tools.org/en/stable/api/reference/scvi.dataloaders.AnnDataLoader.html; 188: https://docs.scvi-tools.org/en/stable/api/reference/scvi.model.SCVI.html

### torchdrug

- [SKILL.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/torchdrug/SKILL.md):
  - home_paths: 94: ~/molecule-datasets/
  - hosts: 59: torchdrug.ai; 64: data.pyg.org; 260: torchdrug.ai; 261: torchdrug.ai; 262: torchdrug.ai; 263: torchdrug.ai; 264: github.com; 274: doi.org; 276: arxiv.org; 278: arxiv.org; 279: export.arxiv.org
  - install: 54: uv pip install; 63: uv pip install; 65: uv pip install
  - outside_writes: 0: potential home/cache write: home-derived path and write/download/dataset operation in this file
  - shell: 31: \`\`\`bash; 51: \`\`\`bash; 62: \`\`\`bash
  - urls: 59: https://torchdrug.ai/docs/installation.html; 64: https://data.pyg.org/whl/torch-2.0.0+cpu.html; 260: https://torchdrug.ai/docs/; 261: https://torchdrug.ai/docs/tutorials/; 262: https://torchdrug.ai/docs/installation.html; 263: https://torchdrug.ai/docs/api/; 264: https://github.com/DeepGraphLearning/torchdrug/releases/tag/v0.2.1; 274: https://doi.org/10.48550/arXiv.2609.00065; 276: https://arxiv.org/abs/2609.00065; 278: https://arxiv.org/abs/2609.00065; 279: http://export.arxiv.org/api/query?id_list=2609.00065
- [references/core_concepts.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/torchdrug/references/core_concepts.md):
  - hosts: 4: torchdrug.ai; 5: torchdrug.ai; 6: torchdrug.ai; 154: torchdrug.ai
  - urls: 4: https://torchdrug.ai/docs/api/data.html; 5: https://torchdrug.ai/docs/quick_start.html; 6: https://torchdrug.ai/docs/notes/; 154: https://torchdrug.ai/docs/notes/reference.html
- [references/datasets.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/torchdrug/references/datasets.md):
  - home_paths: 25: ~/molecule-datasets/; 25: expanduser(; 68: ~/molecule-datasets/; 94: ~/protein-datasets/; 117: ~/kg-datasets/; 134: ~/molecule-datasets/; 139: ~/molecule-datasets/
  - hosts: 4: torchdrug.ai; 28: deepchemdata.s3-us-west-1.amazonaws.com; 241: torchdrug.ai; 242: torchdrug.ai; 243: torchdrug.ai; 244: torchdrug.ai; 245: torchdrug.ai; 246: torchdrug.ai; 247: github.com; 248: github.com
  - outside_writes: 0: potential home/cache write: home-derived path and write/download/dataset operation in this file
  - urls: 4: https://torchdrug.ai/docs/api/datasets.html; 28: https://deepchemdata.s3-us-west-1.amazonaws.com/datasets/clintox.csv.gz; 241: https://torchdrug.ai/docs/api/datasets.html; 242: https://torchdrug.ai/docs/tutorials/property_prediction.html; 243: https://torchdrug.ai/docs/tutorials/pretrain.html; 244: https://torchdrug.ai/docs/tutorials/generation.html; 245: https://torchdrug.ai/docs/tutorials/retrosynthesis.html; 246: https://torchdrug.ai/docs/tutorials/reasoning.html; 247: https://github.com/deepchem/deepchem/blob/master/deepchem/molnet/load_function/clintox_datasets.py; 248: https://github.com/DeepGraphLearning/torchdrug/tree/v0.2.1/torchdrug/datasets
- [references/knowledge_graphs.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/torchdrug/references/knowledge_graphs.md):
  - home_paths: 29: ~/kg-datasets/
  - hosts: 4: torchdrug.ai; 136: torchdrug.ai; 229: torchdrug.ai; 230: torchdrug.ai; 231: torchdrug.ai; 232: torchdrug.ai
  - outside_writes: 0: potential home/cache write: home-derived path and write/download/dataset operation in this file
  - urls: 4: https://torchdrug.ai/docs/tutorials/reasoning.html; 136: https://torchdrug.ai/docs/api/models.html#knowledge-graph-reasoning-models; 229: https://torchdrug.ai/docs/tutorials/reasoning.html; 230: https://torchdrug.ai/docs/api/datasets.html#knowledge-graph-datasets; 231: https://torchdrug.ai/docs/api/models.html#knowledge-graph-reasoning-models; 232: https://torchdrug.ai/docs/api/tasks.html#knowledge-graph-completion
- [references/models_architectures.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/torchdrug/references/models_architectures.md):
  - home_paths: 100: ~/model-weights/esm/
  - hosts: 4: torchdrug.ai; 220: torchdrug.ai; 221: torchdrug.ai; 222: torchdrug.ai; 223: torchdrug.ai; 224: torchdrug.ai; 225: torchdrug.ai
  - outside_writes: 0: potential home/cache write: home-derived path and write/download/dataset operation in this file
  - urls: 4: https://torchdrug.ai/docs/api/models.html; 220: https://torchdrug.ai/docs/api/models.html; 221: https://torchdrug.ai/docs/api/tasks.html; 222: https://torchdrug.ai/docs/tutorials/property_prediction.html; 223: https://torchdrug.ai/docs/tutorials/pretrain.html; 224: https://torchdrug.ai/docs/tutorials/generation.html; 225: https://torchdrug.ai/docs/tutorials/reasoning.html
- [references/molecular_generation.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/torchdrug/references/molecular_generation.md):
  - home_paths: 17: ~/molecule-datasets/
  - hosts: 4: torchdrug.ai; 249: torchdrug.ai; 250: torchdrug.ai; 251: torchdrug.ai; 252: torchdrug.ai
  - outside_writes: 0: potential home/cache write: home-derived path and write/download/dataset operation in this file
  - urls: 4: https://torchdrug.ai/docs/tutorials/generation.html; 249: https://torchdrug.ai/docs/tutorials/generation.html; 250: https://torchdrug.ai/docs/benchmark/generation.html; 251: https://torchdrug.ai/docs/api/tasks.html#molecule-generation-tasks; 252: https://torchdrug.ai/docs/api/models.html#normalizing-flows
- [references/molecular_property_prediction.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/torchdrug/references/molecular_property_prediction.md):
  - home_paths: 23: ~/molecule-datasets/; 147: ~/molecule-datasets/
  - hosts: 4: torchdrug.ai; 6: torchdrug.ai; 256: torchdrug.ai; 257: torchdrug.ai; 258: torchdrug.ai; 259: torchdrug.ai; 260: github.com
  - outside_writes: 0: potential home/cache write: home-derived path and write/download/dataset operation in this file
  - urls: 4: https://torchdrug.ai/docs/tutorials/property_prediction.html; 6: https://torchdrug.ai/docs/tutorials/pretrain.html; 256: https://torchdrug.ai/docs/tutorials/property_prediction.html; 257: https://torchdrug.ai/docs/tutorials/pretrain.html; 258: https://torchdrug.ai/docs/api/tasks.html#property-prediction-tasks; 259: https://torchdrug.ai/docs/api/datasets.html#molecule-property-prediction-datasets; 260: https://github.com/DeepGraphLearning/torchdrug/releases/tag/v0.2.1
- [references/protein_modeling.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/torchdrug/references/protein_modeling.md):
  - home_paths: 85: ~/protein-datasets/; 115: ~/model-weights/esm/
  - hosts: 5: torchdrug.ai; 6: torchdrug.ai; 7: torchdrug.ai; 137: dl.fbaipublicfiles.com; 248: torchdrug.ai; 249: torchdrug.ai; 250: torchdrug.ai; 251: torchdrug.ai; 252: github.com
  - outside_writes: 0: potential home/cache write: home-derived path and write/download/dataset operation in this file
  - urls: 5: https://torchdrug.ai/docs/api/data.html; 6: https://torchdrug.ai/docs/api/datasets.html; 7: https://torchdrug.ai/docs/api/models.html; 248: https://torchdrug.ai/docs/api/data.html#protein; 249: https://torchdrug.ai/docs/api/datasets.html#protein-property-prediction-datasets; 250: https://torchdrug.ai/docs/api/models.html#protein-sequence-encoders; 251: https://torchdrug.ai/docs/api/models.html#graph-neural-networks; 252: https://github.com/DeepGraphLearning/torchdrug/releases/tag/v0.2.1
- [references/retrosynthesis.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/torchdrug/references/retrosynthesis.md):
  - home_paths: 25: ~/molecule-datasets/; 30: ~/molecule-datasets/
  - hosts: 4: torchdrug.ai; 263: torchdrug.ai; 264: torchdrug.ai; 265: torchdrug.ai
  - outside_writes: 0: potential home/cache write: home-derived path and write/download/dataset operation in this file
  - urls: 4: https://torchdrug.ai/docs/tutorials/retrosynthesis.html; 263: https://torchdrug.ai/docs/tutorials/retrosynthesis.html; 264: https://torchdrug.ai/docs/api/tasks.html#retrosynthesis-tasks; 265: https://torchdrug.ai/docs/api/datasets.html#uspto50k
- [references/review.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/torchdrug/references/review.md):
  - hosts: 113: pypi.org; 114: github.com; 115: torchdrug.ai; 116: github.com; 117: torchdrug.ai; 118: torchdrug.ai; 119: torchdrug.ai; 120: torchdrug.ai; 121: github.com; 122: data.pyg.org
  - install: 21: uv pip install; 22: uv pip install; 23: uv pip install
  - shell: 20: \`\`\`bash
  - urls: 113: https://pypi.org/project/torchdrug/0.2.1/; 114: https://github.com/DeepGraphLearning/torchdrug/releases/tag/v0.2.1; 115: https://torchdrug.ai/docs/installation.html; 116: https://github.com/DeepGraphLearning/torchdrug/tree/v0.2.1/torchdrug; 117: https://torchdrug.ai/docs/api/data.html; 118: https://torchdrug.ai/docs/api/tasks.html; 119: https://torchdrug.ai/docs/api/models.html; 120: https://torchdrug.ai/docs/api/core.html; 121: https://github.com/deepchem/deepchem/blob/master/deepchem/molnet/load_function/clintox_datasets.py; 122: https://data.pyg.org/whl/torch-2.0.0+cpu.html; 123: https://docs.astral.sh/uv/concepts/projects/config/#augmenting-build-dependencies

## Fail evidence across the entire pack

### arbor

LLM-provider key reference/read instruction

- [references/arbor-upstream.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/arbor/references/arbor-upstream.md) provider_key: 44: OPENAI_API_KEY; 44: ANTHROPIC_API_KEY

### autoskill

LLM-provider key reference/read instruction; cookie, keychain, SSH or screen access; explicit exclusion: screen recordings

- [SKILL.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/autoskill/SKILL.md) sensitive_access: 77: Screen Recording
- [SKILL.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/autoskill/SKILL.md) provider_key: 20: ANTHROPIC_API_KEY; 32: ANTHROPIC_API_KEY; 121: ANTHROPIC_API_KEY
- [config.yaml](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/autoskill/config.yaml) provider_key: 22: ANTHROPIC_API_KEY
- [scripts/backends.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/autoskill/scripts/backends.py) sensitive_access: 21: screen-capture
- [scripts/backends.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/autoskill/scripts/backends.py) provider_key: 120: ANTHROPIC_API_KEY; 122: ANTHROPIC_API_KEY
- [scripts/doctor.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/autoskill/scripts/doctor.py) provider_key: 51: ANTHROPIC_API_KEY; 52: ANTHROPIC_API_KEY; 53: ANTHROPIC_API_KEY
- [scripts/redact.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/autoskill/scripts/redact.py) provider_key: 11: ANTHROPIC_API_KEY; 11: OPENAI_API_KEY; 12: GOOGLE_API_KEY

### citation-management

explicit exclusion: retained explicit exclusion from the supplied review; no provider-key match at this pin


### datalad

cookie, keychain, SSH or screen access

- [SKILL.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/datalad/SKILL.md) sensitive_access: 240: SSH
- [references/publishing.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/datalad/references/publishing.md) sensitive_access: 38: SSH ; 56: SSH

### etetoolkit

cookie, keychain, SSH or screen access

- [references/visualization.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/etetoolkit/references/visualization.md) sensitive_access: 17: SSH ; 105: ssh

### exa-search

LLM-provider key reference/read instruction

- [SKILL.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/exa-search/SKILL.md) provider_key: 4: EXA_API_KEY; 13: EXA_API_KEY; 15: EXA_API_KEY; 73: EXA_API_KEY; 75: EXA_API_KEY; 86: EXA_API_KEY
- [scripts/exa_extract.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/exa-search/scripts/exa_extract.py) provider_key: 82: EXA_API_KEY; 84: EXA_API_KEY
- [scripts/exa_search.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/exa-search/scripts/exa_search.py) provider_key: 8: EXA_API_KEY; 95: EXA_API_KEY; 97: EXA_API_KEY

### fictiv

cookie, keychain, SSH or screen access

- [references/troubleshooting.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/fictiv/references/troubleshooting.md) sensitive_access: 127: Cookie
- [references/ui-map.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/fictiv/references/ui-map.md) sensitive_access: 193: Cookie

### generate-image

LLM-provider key reference/read instruction

- [SKILL.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/generate-image/SKILL.md) provider_key: 5: OPENROUTER_API_KEY; 12: OPENROUTER_API_KEY; 14: OPENROUTER_API_KEY; 38: OPENROUTER_API_KEY; 39: OPENROUTER_API_KEY; 244: OPENROUTER_API_KEY
- [scripts/generate_image.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/generate-image/scripts/generate_image.py) provider_key: 109: OPENROUTER_API_KEY; 129: OPENROUTER_API_KEY; 135: OPENROUTER_API_KEY; 136: OPENROUTER_API_KEY; 137: OPENROUTER_API_KEY; 720: OPENROUTER_API_KEY

### gget

LLM-provider key reference/read instruction

- [references/module_catalog.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/gget/references/module_catalog.md) provider_key: 719: OPENAI_API_KEY
- [references/module_reference.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/gget/references/module_reference.md) provider_key: 517: OPENAI_API_KEY; 527: OPENAI_API_KEY

### hypogenic

LLM-provider key reference/read instruction

- [SKILL.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/hypogenic/SKILL.md) provider_key: 115: OPENAI_API_KEY; 115: ANTHROPIC_API_KEY
- [assets/run_config.example.json](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/hypogenic/assets/run_config.example.json) provider_key: 12: OPENAI_API_KEY
- [references/configuration.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/hypogenic/references/configuration.md) provider_key: 75: OPENAI_API_KEY; 76: ANTHROPIC_API_KEY
- [references/security.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/hypogenic/references/security.md) provider_key: 42: OPENAI_API_KEY; 43: ANTHROPIC_API_KEY
- [references/upstream.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/hypogenic/references/upstream.md) provider_key: 82: OPENAI_API_KEY; 83: ANTHROPIC_API_KEY
- [scripts/_common.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/hypogenic/scripts/_common.py) provider_key: 54: OPENAI_API_KEY; 55: ANTHROPIC_API_KEY

### infographics

LLM-provider key reference/read instruction

- [SKILL.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/infographics/SKILL.md) provider_key: 4: OPENROUTER_API_KEY; 11: OPENROUTER_API_KEY; 13: OPENROUTER_API_KEY; 48: OPENROUTER_API_KEY; 281: OPENROUTER_API_KEY
- [references/iterative_refinement.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/infographics/references/iterative_refinement.md) provider_key: 131: OPENROUTER_API_KEY
- [scripts/generate_infographic.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/infographics/scripts/generate_infographic.py) provider_key: 67: OPENROUTER_API_KEY; 85: OPENROUTER_API_KEY; 97: OPENROUTER_API_KEY; 192: OPENROUTER_API_KEY; 213: OPENROUTER_API_KEY; 246: OPENROUTER_API_KEY; 250: OPENROUTER_API_KEY; 251: OPENROUTER_API_KEY
- [scripts/generate_infographic_ai.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/infographics/scripts/generate_infographic_ai.py) provider_key: 13: OPENROUTER_API_KEY; 127: OPENROUTER_API_KEY; 145: OPENROUTER_API_KEY; 421: OPENROUTER_API_KEY; 422: OPENROUTER_API_KEY; 423: OPENROUTER_API_KEY; 1286: OPENROUTER_API_KEY; 1307: OPENROUTER_API_KEY; 1325: OPENROUTER_API_KEY; 1327: OPENROUTER_API_KEY; 1328: OPENROUTER_API_KEY

### labarchive-integration

cookie, keychain, SSH or screen access

- [references/authentication_guide.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/labarchive-integration/references/authentication_guide.md) sensitive_access: 110: keychain

### latex-posters

LLM-provider key reference/read instruction

- [SKILL.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/latex-posters/SKILL.md) provider_key: 5: OPENROUTER_API_KEY; 11: OPENROUTER_API_KEY; 13: OPENROUTER_API_KEY; 171: OPENROUTER_API_KEY
- [references/ai_graphics_for_posters.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/latex-posters/references/ai_graphics_for_posters.md) provider_key: 36: OPENROUTER_API_KEY
- [scripts/generate_schematic.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/latex-posters/scripts/generate_schematic.py) provider_key: 54: OPENROUTER_API_KEY; 72: OPENROUTER_API_KEY; 84: OPENROUTER_API_KEY; 130: OPENROUTER_API_KEY; 145: OPENROUTER_API_KEY; 162: OPENROUTER_API_KEY; 166: OPENROUTER_API_KEY; 167: OPENROUTER_API_KEY
- [scripts/generate_schematic_ai.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/latex-posters/scripts/generate_schematic_ai.py) provider_key: 12: OPENROUTER_API_KEY; 125: OPENROUTER_API_KEY; 143: OPENROUTER_API_KEY; 223: OPENROUTER_API_KEY; 231: OPENROUTER_API_KEY; 232: OPENROUTER_API_KEY; 233: OPENROUTER_API_KEY; 791: OPENROUTER_API_KEY; 804: OPENROUTER_API_KEY; 813: OPENROUTER_API_KEY; 815: OPENROUTER_API_KEY; 816: OPENROUTER_API_KEY

### literature-review

LLM-provider key reference/read instruction

- [SKILL.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/literature-review/SKILL.md) provider_key: 6: OPENROUTER_API_KEY; 12: OPENROUTER_API_KEY; 14: OPENROUTER_API_KEY; 42: OPENROUTER_API_KEY; 180: PARALLEL_API_KEY
- [references/search_and_citation.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/literature-review/references/search_and_citation.md) provider_key: 10: PARALLEL_API_KEY
- [scripts/generate_schematic.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/literature-review/scripts/generate_schematic.py) provider_key: 54: OPENROUTER_API_KEY; 72: OPENROUTER_API_KEY; 84: OPENROUTER_API_KEY; 130: OPENROUTER_API_KEY; 145: OPENROUTER_API_KEY; 162: OPENROUTER_API_KEY; 166: OPENROUTER_API_KEY; 167: OPENROUTER_API_KEY
- [scripts/generate_schematic_ai.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/literature-review/scripts/generate_schematic_ai.py) provider_key: 12: OPENROUTER_API_KEY; 125: OPENROUTER_API_KEY; 143: OPENROUTER_API_KEY; 223: OPENROUTER_API_KEY; 231: OPENROUTER_API_KEY; 232: OPENROUTER_API_KEY; 233: OPENROUTER_API_KEY; 791: OPENROUTER_API_KEY; 804: OPENROUTER_API_KEY; 813: OPENROUTER_API_KEY; 815: OPENROUTER_API_KEY; 816: OPENROUTER_API_KEY

### markdown-mermaid-writing

cookie, keychain, SSH or screen access

- [references/diagrams/complex_examples.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/markdown-mermaid-writing/references/diagrams/complex_examples.md) sensitive_access: 224: cookies; 229: cookies
- [references/diagrams/sequence.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/markdown-mermaid-writing/references/diagrams/sequence.md) sensitive_access: 38: cookie

### markitdown

LLM-provider key reference/read instruction; cookie, keychain, SSH or screen access

- [references/cloud_and_ocr.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/markitdown/references/cloud_and_ocr.md) provider_key: 72: OPENAI_API_KEY
- [references/file_formats.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/markitdown/references/file_formats.md) sensitive_access: 207: cookies
- [references/mcp_and_plugins.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/markitdown/references/mcp_and_plugins.md) sensitive_access: 79: SSH

### modal

LLM-provider key reference/read instruction

- [references/secrets.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/modal/references/secrets.md) provider_key: 76: OPENAI_API_KEY; 123: OPENAI_API_KEY

### neuropixels-analysis

LLM-provider key reference/read instruction

- [SKILL.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/neuropixels-analysis/SKILL.md) provider_key: 11: ANTHROPIC_API_KEY; 13: ANTHROPIC_API_KEY; 267: ANTHROPIC_API_KEY
- [references/AI_CURATION.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/neuropixels-analysis/references/AI_CURATION.md) provider_key: 15: ANTHROPIC_API_KEY; 60: ANTHROPIC_API_KEY; 95: OPENAI_API_KEY
- [references/standard_workflow.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/neuropixels-analysis/references/standard_workflow.md) provider_key: 230: ANTHROPIC_API_KEY

### nextflow

fetches and runs remote code

- [references/testing.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/nextflow/references/testing.md) remote_execution: 0: download followed by execution

### omero-integration

cookie, keychain, SSH or screen access

- [references/advanced.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/omero-integration/references/advanced.md) sensitive_access: 219: cookies; 222: cookies
- [references/sources.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/omero-integration/references/sources.md) sensitive_access: 50: cookies; 190: cookies

### open-notebook

LLM-provider key reference/read instruction

- [references/configuration.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/open-notebook/references/configuration.md) provider_key: 72: OPENAI_API_KEY; 72: ANTHROPIC_API_KEY; 73: GOOGLE_API_KEY; 73: GROQ_API_KEY; 98: OPENAI_API_KEY

### paperclip

cookie, keychain, SSH or screen access; pipe-to-shell installation; explicit exclusion: browser cookies, uploads and pipe-to-shell installation

- [SKILL.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/paperclip/SKILL.md) sensitive_access: 191: cookie
- [references/cli-reference.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/paperclip/references/cli-reference.md) sensitive_access: 157: cookies
- [references/installation.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/paperclip/references/installation.md) pipe_to_shell: 13: curl -fsSL https://paperclip.gxl.ai/install.sh \| bash
- [references/repos-and-workspace.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/paperclip/references/repos-and-workspace.md) sensitive_access: 188: cookies; 190: cookie

### parallel-web

LLM-provider key reference/read instruction

- [SKILL.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/parallel-web/SKILL.md) provider_key: 11: PARALLEL_API_KEY; 13: PARALLEL_API_KEY; 65: PARALLEL_API_KEY; 117: PARALLEL_API_KEY; 117: PARALLEL_API_KEY
- [references/api-contracts.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/parallel-web/references/api-contracts.md) provider_key: 13: PARALLEL_API_KEY

### pi-agent

LLM-provider key reference/read instruction; cookie, keychain, SSH or screen access; pipe-to-shell installation; settings or hook instruction; explicit exclusion: pipe-to-shell installation

- [references/containerization.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/pi-agent/references/containerization.md) provider_key: 56: ANTHROPIC_API_KEY
- [references/environment-variables.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/pi-agent/references/environment-variables.md) sensitive_access: 56: SSH
- [references/overview.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/pi-agent/references/overview.md) pipe_to_shell: 28: curl -fsSL https://pi.dev/install.sh \| sh
- [references/overview.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/pi-agent/references/overview.md) provider_key: 33: ANTHROPIC_API_KEY
- [references/packages.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/pi-agent/references/packages.md) sensitive_access: 42: SSH ; 42: .ssh/; 42: ssh
- [references/packages.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/pi-agent/references/packages.md) settings_hooks: 31: install\`/\`remove\` write to user settings by default; \`-l\` writes to project settings (\`.pi/settings.json
- [references/pi-interview.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/pi-agent/references/pi-interview.md) sensitive_access: 28: ssh ; 28: SSH
- [references/pi-web-access.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/pi-agent/references/pi-web-access.md) sensitive_access: 5: cookies; 31: cookie; 58: cookies; 58: cookie; 104: cookies; 104: BROWSER_COOKIES; 106: cookies
- [references/providers.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/pi-agent/references/providers.md) provider_key: 16: XAI_API_KEY; 26: ANTHROPIC_API_KEY; 28: AZURE_OPENAI_API_KEY; 29: OPENAI_API_KEY; 30: DEEPSEEK_API_KEY; 32: GEMINI_API_KEY; 38: MISTRAL_API_KEY; 39: GROQ_API_KEY; 43: XAI_API_KEY; 44: OPENROUTER_API_KEY; 50: FIREWORKS_API_KEY; 51: TOGETHER_API_KEY; 107: AZURE_OPENAI_API_KEY; 130: ANTHROPIC_OAUTH_TOKEN; 130: ANTHROPIC_AUTH_TOKEN
- [references/quickstart.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/pi-agent/references/quickstart.md) provider_key: 31: ANTHROPIC_API_KEY
- [references/shell-aliases.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/pi-agent/references/shell-aliases.md) settings_hooks: 14: configure \`~/.pi/agent/settings.json
- [references/terminal-setup.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/pi-agent/references/terminal-setup.md) settings_hooks: 74: Add to \`settings.json

### research-grants

LLM-provider key reference/read instruction

- [SKILL.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/research-grants/SKILL.md) provider_key: 6: OPENROUTER_API_KEY; 71: OPENROUTER_API_KEY

### research-lookup

LLM-provider key reference/read instruction

- [README.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/research-lookup/README.md) provider_key: 31: PARALLEL_API_KEY; 31: OPENROUTER_API_KEY; 33: PARALLEL_API_KEY
- [SKILL.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/research-lookup/SKILL.md) provider_key: 5: PARALLEL_API_KEY; 5: OPENROUTER_API_KEY; 11: PARALLEL_API_KEY; 13: PARALLEL_API_KEY; 16: OPENROUTER_API_KEY; 247: PARALLEL_API_KEY; 278: OPENROUTER_API_KEY; 329: PARALLEL_API_KEY; 329: PARALLEL_API_KEY
- [references/api-contracts.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/research-lookup/references/api-contracts.md) provider_key: 12: PARALLEL_API_KEY
- [scripts/research_lookup.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/research-lookup/scripts/research_lookup.py) provider_key: 213: PARALLEL_API_KEY; 214: OPENROUTER_API_KEY; 223: PARALLEL_API_KEY; 227: OPENROUTER_API_KEY; 236: PARALLEL_API_KEY; 236: OPENROUTER_API_KEY; 746: PARALLEL_API_KEY; 749: PARALLEL_API_KEY; 802: OPENROUTER_API_KEY; 804: OPENROUTER_API_KEY

### scientific-critical-thinking

LLM-provider key reference/read instruction

- [SKILL.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/scientific-critical-thinking/SKILL.md) provider_key: 6: OPENROUTER_API_KEY; 69: OPENROUTER_API_KEY

### scientific-schematics

LLM-provider key reference/read instruction

- [SKILL.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/scientific-schematics/SKILL.md) provider_key: 12: OPENROUTER_API_KEY; 14: OPENROUTER_API_KEY; 54: OPENROUTER_API_KEY; 96: OPENROUTER_API_KEY; 280: OPENROUTER_API_KEY; 281: OPENROUTER_API_KEY; 362: OPENROUTER_API_KEY
- [references/iterative_refinement.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/scientific-schematics/references/iterative_refinement.md) provider_key: 198: OPENROUTER_API_KEY; 200: OPENROUTER_API_KEY
- [scripts/example_usage.sh](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/scientific-schematics/scripts/example_usage.sh) provider_key: 5: OPENROUTER_API_KEY; 21: OPENROUTER_API_KEY; 22: OPENROUTER_API_KEY; 25: OPENROUTER_API_KEY; 29: OPENROUTER_API_KEY
- [scripts/generate_schematic.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/scientific-schematics/scripts/generate_schematic.py) provider_key: 54: OPENROUTER_API_KEY; 72: OPENROUTER_API_KEY; 84: OPENROUTER_API_KEY; 130: OPENROUTER_API_KEY; 145: OPENROUTER_API_KEY; 162: OPENROUTER_API_KEY; 166: OPENROUTER_API_KEY; 167: OPENROUTER_API_KEY
- [scripts/generate_schematic_ai.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/scientific-schematics/scripts/generate_schematic_ai.py) provider_key: 12: OPENROUTER_API_KEY; 125: OPENROUTER_API_KEY; 143: OPENROUTER_API_KEY; 223: OPENROUTER_API_KEY; 231: OPENROUTER_API_KEY; 232: OPENROUTER_API_KEY; 233: OPENROUTER_API_KEY; 791: OPENROUTER_API_KEY; 804: OPENROUTER_API_KEY; 813: OPENROUTER_API_KEY; 815: OPENROUTER_API_KEY; 816: OPENROUTER_API_KEY

### scientific-slides

LLM-provider key reference/read instruction

- [SKILL.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/scientific-slides/SKILL.md) provider_key: 6: OPENROUTER_API_KEY; 12: OPENROUTER_API_KEY; 14: OPENROUTER_API_KEY
- [references/script_reference.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/scientific-slides/references/script_reference.md) provider_key: 17: OPENROUTER_API_KEY; 70: OPENROUTER_API_KEY; 83: OPENROUTER_API_KEY
- [scripts/generate_schematic.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/scientific-slides/scripts/generate_schematic.py) provider_key: 54: OPENROUTER_API_KEY; 72: OPENROUTER_API_KEY; 84: OPENROUTER_API_KEY; 130: OPENROUTER_API_KEY; 145: OPENROUTER_API_KEY; 162: OPENROUTER_API_KEY; 166: OPENROUTER_API_KEY; 167: OPENROUTER_API_KEY
- [scripts/generate_schematic_ai.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/scientific-slides/scripts/generate_schematic_ai.py) provider_key: 12: OPENROUTER_API_KEY; 125: OPENROUTER_API_KEY; 143: OPENROUTER_API_KEY; 223: OPENROUTER_API_KEY; 231: OPENROUTER_API_KEY; 232: OPENROUTER_API_KEY; 233: OPENROUTER_API_KEY; 791: OPENROUTER_API_KEY; 804: OPENROUTER_API_KEY; 813: OPENROUTER_API_KEY; 815: OPENROUTER_API_KEY; 816: OPENROUTER_API_KEY
- [scripts/generate_slide_image.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/scientific-slides/scripts/generate_slide_image.py) provider_key: 57: OPENROUTER_API_KEY; 75: OPENROUTER_API_KEY; 87: OPENROUTER_API_KEY; 131: OPENROUTER_API_KEY; 143: OPENROUTER_API_KEY; 155: OPENROUTER_API_KEY; 159: OPENROUTER_API_KEY; 160: OPENROUTER_API_KEY
- [scripts/generate_slide_image_ai.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/scientific-slides/scripts/generate_slide_image_ai.py) provider_key: 19: OPENROUTER_API_KEY; 138: OPENROUTER_API_KEY; 156: OPENROUTER_API_KEY; 252: OPENROUTER_API_KEY; 259: OPENROUTER_API_KEY; 260: OPENROUTER_API_KEY; 261: OPENROUTER_API_KEY; 762: OPENROUTER_API_KEY; 774: OPENROUTER_API_KEY; 782: OPENROUTER_API_KEY; 784: OPENROUTER_API_KEY; 785: OPENROUTER_API_KEY

### waypoint-bio

fetches and runs remote code

- [references/python-api.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/waypoint-bio/references/python-api.md) remote_execution: 36: from_pretrained call enables trust_remote_code=True
- [scripts/vocab_coverage.py](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/waypoint-bio/scripts/vocab_coverage.py) remote_execution: 95: from_pretrained call enables trust_remote_code=True; 105: from_pretrained call enables trust_remote_code=True
