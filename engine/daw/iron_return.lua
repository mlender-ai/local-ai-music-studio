-- One render graph for the master and instrument isolation controls.
local r=reaper
local dir=assert(({r.get_action_context()})[2]:match("^(.*[/\\])"))
local f=dofile(dir.."rock_fx.lua")
local bar=240/108
local function build()
  r.Main_OnCommand(40859,0)
  local p=assert(r.EnumProjects(-1))
  assert(r.CountTracks(p)==0)
  r.SetCurrentBPM(p,108,false)
  local t, order = {},{}
  local function track(key,label,db,pan)
    local idx=r.CountTracks(p);r.InsertTrackAtIndex(idx,true)
    t[key]=r.GetTrack(p,idx);order[#order+1]=key
    r.GetSetMediaTrackInfo_String(t[key],"P_NAME",label,true)
    r.SetMediaTrackInfo_Value(t[key],"D_VOL",f.amp(db))
    r.SetMediaTrackInfo_Value(t[key],"D_PAN",pan)
    return t[key]
  end
  local function item(dst,file,pos,span,offset,rate,pitch,vol,edge)
    local src=assert(r.PCM_Source_CreateFromFile(dir.."Audio/"..file..".wav"),file)
    local it=assert(r.AddMediaItemToTrack(dst));local take=assert(r.AddTakeToMediaItem(it))
    r.SetMediaItemTake_Source(take,src)
    for k,v in pairs({D_POSITION=pos,D_LENGTH=span,D_FADEINLEN=edge,D_FADEOUTLEN=edge,B_LOOPSRC=0,D_VOL=f.amp(vol)}) do r.SetMediaItemInfo_Value(it,k,v) end
    for k,v in pairs({D_STARTOFFS=offset,D_PLAYRATE=rate,B_PPITCH=1,D_PITCH=pitch}) do r.SetMediaItemTakeInfo_Value(take,k,v) end
    r.GetSetMediaItemTakeInfo_String(take,"P_NAME",file,true)
  end
  local dur=48*bar+1.65
  local regions,fxlog={},assert(io.open(dir.."fx.tsv","w"))
  local trim
  for l in io.lines(dir.."layout.tsv") do
    local c={};for token in l:gmatch("[^\t]+") do c[#c+1]=token end
    if c[1]=="track" then track(c[2],c[3],tonumber(c[4]),tonumber(c[5]))
    elseif c[1]=="item" then item(t[c[2]],c[3],tonumber(c[4]),tonumber(c[5]),tonumber(c[6]),tonumber(c[7]),tonumber(c[8]),tonumber(c[9]),tonumber(c[10]))
    elseif c[1]=="bar" then r.AddProjectMarker2(p,false,(tonumber(c[2])-1)*bar,0,c[2].."   "..c[3],-1,0)
    elseif c[1]=="region" then r.AddProjectMarker2(p,true,(c[3]-1)*bar,c[4]*bar,c[2],-1,0)
    elseif c[1]=="trim" then trim=assert(tonumber(c[2])) end
  end
  -- Select the cabinet by its host-reported name; numeric file indices depend on installation.
  local function rig(key,model,gain,hard,ceiling)
    local tr=t[key];local drive=f.fx(tr,"JS: guitar/distortion")
    f.displayed(tr,drive,0,gain);f.displayed(tr,drive,1,hard);f.displayed(tr,drive,2,ceiling)
    local cab=f.fx(tr,"JS: guitar/amp-model")
    local _,lo,hi=r.TrackFX_GetParam(tr,cab,0)
    local found=false
    for i=math.floor(lo),math.floor(hi) do
      r.TrackFX_SetParam(tr,cab,0,i)
      local _,v=r.TrackFX_GetFormattedParamValue(tr,cab,0)
      if v==model then found=true;break end
    end
    assert(found,model.." is missing")
    f.displayed(tr,cab,1,-2)
    f.eq(tr,key=="lead-di" and 105 or 66,290,-1.3,3600,.55)
  end
  rig("left-di","Marshall JCM800 - Marshall Stock 70",28,6,-10)
  rig("right-di","Marshall JCM800 - Matchless Chieftain",25,5,-10)
  rig("lead-di","Marshall JTM45 - Matchless Chieftain",31,5,-9)
  f.eq(t.bass,30,215,-1.1)
  f.compression(t.bass,-15,2.2,24,105)
  f.eq(t.kit,27,380,-1,3900,.8)
  f.compression(t.kit,-10,1.6,23,90)
  f.eq(t["generated-guitar"],90,450,-1)
  local room=track("room","Short live room",0,0);f.room(room,27,54,9,220,6200)
  local hall=track("hall","Guitar hall and modulation",0,0);f.eq(hall,260,500,-1.6)
  f.room(hall,88,64,43,300,5800);f.fx(hall,"JS: sstillwell/chorus_stereo")
  local echo=track("echo","Lead feedback delay",0,0)
  local d=f.fx(echo,"ReaDelay");f.set(echo,d,1,0);f.displayed(echo,d,0,0)
  f.displayed(echo,d,3,45000/108);f.set(echo,d,4,0);f.displayed(echo,d,5,-8.5)
  f.displayed(echo,d,6,4500);f.displayed(echo,d,7,310)
  f.send(t.kit,room,-19);f.send(t["generated-drums"],room,-21)
  f.send(t["right-di"],hall,-17);f.send(t["generated-guitar"],hall,-12)
  f.send(t["lead-di"],echo,-12);f.send(t["lead-di"],hall,-18)
  local function envelope(tr,points)
    local base=r.GetMediaTrackInfo_Value(tr,"D_VOL")
    r.SetOnlyTrackSelected(tr);r.Main_OnCommand(40406,0)
    local env=assert(r.GetTrackEnvelopeByName(tr,"Volume"))
    r.DeleteEnvelopePointRange(env,-1,dur+1)
    for _,pt in ipairs(points) do
      r.InsertEnvelopePoint(env,pt[1],r.ScaleToEnvelopeMode(r.GetEnvelopeScalingMode(env),base*pt[2]),0,0,false,true)
    end
    r.Envelope_SortPoints(env)
  end
  for _,bus in ipairs({hall,echo,room}) do
    local solo=bus==echo and 1.35 or bus==hall and .72 or .82
    envelope(bus,{{0,.36},{14*bar-.10,.22},{14*bar,1.15},{22*bar-.12,1.15},{22*bar,.3},
      {26*bar-.1,.45},{26*bar,solo},{32*bar,solo},{34*bar-.21,solo*1.15},{34*bar-.075,0},
      {38*bar,0},{38*bar+.075,1.20},{46*bar-.1,1.20},{46*bar,.95},{dur, .62}})
  end
  -- Post-amp rides keep pick articulation intact. Leave the solo and bridge at unity.
  for _,k in ipairs({"left-di","right-di","generated-guitar","kit","generated-drums","bass"}) do
    local lift=f.amp((k=="kit" or k=="generated-drums") and 3.7 or k=="bass" and 2.8 or 1.9)
    envelope(t[k],{{0,.66},{2*bar-.08,.66},{2*bar,1},{38*bar-.065,1},
      {38*bar,lift},{46*bar-.09,lift},{46*bar,.79},{47*bar,.78},{48*bar,.62},{dur,.55}})
  end
  local master=r.GetMasterTrack(p)
  r.SetMediaTrackInfo_Value(master,"D_VOL",f.amp(trim))
  for _,key in ipairs(order) do
    for i=0,r.TrackFX_GetCount(t[key])-1 do
      local _,name=r.TrackFX_GetFXName(t[key],i)
      for j=0,r.TrackFX_GetNumParams(t[key],i)-1 do
        local _,parm=r.TrackFX_GetParamName(t[key],i,j);local _,v=r.TrackFX_GetFormattedParamValue(t[key],i,j)
        fxlog:write(key,"\t",name,"\t",parm,"\t",v,"\n")
      end
    end
  end
  fxlog:close()
  for k,v in pairs({RENDER_SETTINGS=0,RENDER_BOUNDSFLAG=0,RENDER_STARTPOS=0,RENDER_ENDPOS=dur,RENDER_TAILFLAG=0,RENDER_SRATE=48000,RENDER_CHANNELS=2}) do r.GetSetProjectInfo(p,k,v,true) end
  r.GetSetProjectInfo_String(p,"RENDER_FILE","",true)
  r.GetSetProjectInfo_String(p,"RENDER_FORMAT","ZXZhdxgAAA==",true)
  local function save(name,allowed)
    for _,k in ipairs(order) do r.SetMediaTrackInfo_Value(t[k],"B_MUTE",(k=="original" or (allowed and not allowed[k])) and 1 or 0) end
    r.GetSetProjectInfo_String(p,"RENDER_PATTERN",name,true)
    r.Main_SaveProjectEx(p,dir..name..".RPP",0)
  end
  save("Drums",{kit=true,["generated-drums"]=true})
  save("Bass",{bass=true})
  save("Lead",{["lead-di"]=true})
  save("Guitars",{["left-di"]=true,["right-di"]=true,["lead-di"]=true,["generated-guitar"]=true})
  save("Rhythm section",{kit=true,bass=true,["generated-drums"]=true})
  save("Iron Return",nil)
  return r.GetAppVersion()
end
local ok,msg=xpcall(build,debug.traceback)
local out=assert(io.open(dir.."host-status.tmp","w"));out:write(ok and "BUILT\n" or "ERROR\n",msg,"\n");out:close()
assert(os.rename(dir.."host-status.tmp",dir.."host-status.txt"))
