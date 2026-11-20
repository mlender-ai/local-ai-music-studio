-- Run in a dedicated REAPER instance with a copied script. Results go beside the script.
local r=reaper
local d=({r.get_action_context()})[2]:match("^(.*/)")
r.Main_OnCommand(40859,0)
local p = r.EnumProjects(-1)
r.InsertTrackAtIndex(0,true)
local t=r.GetTrack(p,0)
local f=assert(io.open(d.."inventory.tsv","w"))
f:write("REAPER\t",r.GetAppVersion(),"\n")
for i=0,10000 do
  local ok,name,ident=r.EnumInstalledFX(i)
  if not ok then break end
  f:write("installed\t",name,"\t",ident,"\n")
end
for _,target in ipairs({"ReaEQ","ReaComp","ReaVerbate","ReaDelay","ReaVerb","ReaLimit","JS: LOSER/Saturation","JS: guitar/distortion","JS: guitar/amp-model","JS: Liteon/deesser","JS: sstillwell/chorus_stereo","JS: loser/stereoEnhancer"}) do
  local ix=r.TrackFX_AddByName(t,target,false,-1)
  f:write("load\t",target,"\t",ix,"\n")
  if ix>=0 then
    for _,key in ipairs({"fx_name","fx_type","fx_ident","version","vendor"}) do
      local ok,val=r.TrackFX_GetNamedConfigParm(t,ix,key)
      if ok then f:write("meta\t",target,"\t",key,"\t",val,"\n") end
    end
    local ixPreset,n=r.TrackFX_GetPresetIndex(t,ix)
    f:write("presets\t",target,"\t",ixPreset,"\t",n,"\n")
    for j=0,r.TrackFX_GetNumParams(t,ix)-1 do
      local _,label=r.TrackFX_GetParamName(t,ix,j)
      local _,v=r.TrackFX_GetFormattedParamValue(t,ix,j)
      f:write("param\t",target,"\t",j,"\t",label,"\t",v,"\t",r.TrackFX_GetParamNormalized(t,ix,j),"\t",tostring(r.GetFXEnvelope(t,ix,j,true)~=nil),"\n")
    end
  end
end
f:close()
local status=assert(io.open(d.."host-status.tmp","w"))
status:write("BUILT\n",r.GetAppVersion(),"\n")
status:close()
assert(os.rename(d.."host-status.tmp", d.."host-status.txt"))
