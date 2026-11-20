-- REAPER host for the V5 audio project. No MIDI or sampler tracks are created.
local r = reaper
local dir = assert(({r.get_action_context()})[2]:match("^(.*[/\\])"))
local lib = dofile(dir.."rock_fx.lua")
local amp,fx,set,displayed,eq = lib.amp,lib.fx,lib.set,lib.displayed,lib.eq
local compression,send,room,automation = lib.compression,lib.send,lib.room,lib.automation
local function build()
  local cfg,sections,inputs={}, {}, {}
  for line in io.lines(dir.."mix.tsv") do
    local kind,a,b,c=line:match("^([^\t]+)\t([^\t]+)\t([^\t]+)\t?(.*)$")
    if kind=="setting" then cfg[a]=assert(tonumber(b))
    elseif kind=="region" then sections[a]={tonumber(b),tonumber(c)}
    elseif kind=="track" then inputs[#inputs+1]={a,b} end
  end
  r.Main_OnCommand(40859,0)
  local proj=assert(r.EnumProjects(-1))
  assert(r.CountTracks(proj)==0)
  r.SetCurrentBPM(proj,cfg.bpm,false)
  local function track(name)
    local n=r.CountTracks(proj)
    r.InsertTrackAtIndex(n,true)
    local t=r.GetTrack(proj,n)
    r.GetSetMediaTrackInfo_String(t,"P_NAME",name,true)
    return t
  end
  local function audio(t,file,startpos,endpos,fade)
    local pcm=assert(r.PCM_Source_CreateFromFile(dir.."Audio/"..file))
    local item=assert(r.AddMediaItemToTrack(t))
    local take=assert(r.AddTakeToMediaItem(item))
    r.SetMediaItemTake_Source(take,pcm)
    r.SetMediaItemInfo_Value(item,"D_POSITION",startpos)
    r.SetMediaItemInfo_Value(item,"D_LENGTH",endpos-startpos)
    r.SetMediaItemInfo_Value(item,"D_FADEINLEN",fade)
    r.SetMediaItemInfo_Value(item,"D_FADEOUTLEN",fade)
    r.SetMediaItemTakeInfo_Value(take,"D_STARTOFFS",startpos)
    r.GetSetMediaItemTakeInfo_String(take,"P_NAME",file,true)
  end
  local t={}
  for _,row in ipairs(inputs) do
    t[row[1]]=track(row[2])
    audio(t[row[1]],row[1]..".wav",0,cfg.source_seconds,0)
  end
  local labels={"Intro","Verse","Pre-chorus","Chorus","Break","Solo cue","Final chorus","Outro"}
  for _,label in ipairs(labels) do
    local span=sections[label]
    assert(span and span[2]>span[1],"Missing region "..label)
    r.AddProjectMarker2(proj,true,span[1],span[2],label,-1,0)
  end
  local function render_settings(pattern,length)
    r.GetSetProjectInfo(proj,"RENDER_SETTINGS",0,true)
    r.GetSetProjectInfo(proj,"RENDER_BOUNDSFLAG",0,true)
    r.GetSetProjectInfo(proj,"RENDER_STARTPOS",0,true)
    r.GetSetProjectInfo(proj,"RENDER_ENDPOS",length,true)
    r.GetSetProjectInfo(proj,"RENDER_TAILFLAG",0,true)
    r.GetSetProjectInfo(proj,"RENDER_SRATE",48000,true)
    r.GetSetProjectInfo(proj,"RENDER_CHANNELS",2,true)
    r.GetSetProjectInfo_String(proj,"RENDER_FILE","",true)
    r.GetSetProjectInfo_String(proj,"RENDER_PATTERN",pattern,true)
    r.GetSetProjectInfo_String(proj,"RENDER_FORMAT","ZXZhdxgAAA==",true)
  end
  render_settings("Dry",cfg.source_seconds)
  r.Main_SaveProjectEx(proj,dir.."Dry.RPP",0)

  local master=r.GetMasterTrack(proj)
  r.SetMediaTrackInfo_Value(master,"D_VOL",amp(cfg.master_db))
  eq(master,26,315,-0.7,6800,0.45)
  if t.vocals then
    eq(t.vocals,78,285,-1.4,3950,1.05)
    local de=fx(t.vocals,"JS: Liteon/deesser")
    set(t.vocals,de,0,0) -- Stereo mode
    displayed(t.vocals,de,3,6600)
    displayed(t.vocals,de,5,-25)
    displayed(t.vocals,de,6,2.0)
    set(t.vocals,de,10,0.32)
    compression(t.vocals,-15,1.35,19,110)
    r.SetMediaTrackInfo_Value(t.vocals,"D_VOL",amp(cfg.vocal_db))
  end
  if t.drums then compression(t.drums,-12,1.4,25,95) end
  if t.bass then eq(t.bass,30,215,-0.7) end

  local ambience=track("Room · drums and clean guitar")
  room(ambience,31,62,8,210,6900)
  local plate=track("Plate-style · vocal reflections")
  room(plate,52,57,32,270,7400)
  local haze=track("Shoegaze · diffuse guitar return")
  local reverb=room(haze,86,68,42,300,6500)
  local chorus_fx=fx(haze,"JS: sstillwell/chorus_stereo")
  for p,value in ipairs({14,2,0.32,0.42,-17,0,0.09}) do
    displayed(haze,chorus_fx,p-1,value)
  end
  local delay=track("Delay · dotted eighth")
  local tap=fx(delay,"ReaDelay")
  set(delay,tap,1,0)
  displayed(delay,tap,0,0)
  displayed(delay,tap,3,45000/cfg.bpm)
  set(delay,tap,4,0)
  displayed(delay,tap,5,-12)
  displayed(delay,tap,6,4300)
  displayed(delay,tap,7,300)
  local guitar=t.guitar or t.stereo
  if t.guitar then eq(guitar,96,335,-1.6,4900,0.75) end
  send(guitar,ambience,-23)
  send(guitar,haze,cfg.haze_db)
  send(guitar,delay,-25)
  if t.vocals then send(t.vocals,plate,cfg.plate_db) end
  if t.drums then send(t.drums,ambience,-25) end
  local pre,chorus,solo,final,outro=sections["Pre-chorus"][1],sections.Chorus[1],sections["Solo cue"],sections["Final chorus"][1],sections.Outro[1]
  automation(haze,reverb,0,{{0,-9},{sections.Verse[1],-18},{pre,-17},
      {chorus-0.22,-9},{chorus,cfg.chorus_wet_db},{sections.Break[1]-0.35,cfg.chorus_wet_db},
      {sections.Break[1],-14},{solo[1],-9},{final-0.22,-9},
      {final,cfg.chorus_wet_db},{outro-0.35,cfg.chorus_wet_db},{outro,-3},{cfg.source_seconds,-5}})
  if t.guitar then
    local width=fx(guitar,"JS: loser/stereoEnhancer")
    displayed(guitar,width,1,550)
    local points={{0,100}}
    for _,span in ipairs({sections.Chorus,sections["Final chorus"]}) do
      points[#points+1]={span[1]-0.21,100}
      points[#points+1]={span[1],cfg.chorus_width}
      points[#points+1]={span[2]-0.21,cfg.chorus_width}
      points[#points+1]={span[2],100}
    end
    automation(guitar,width,2,points)
  end
  if t.guitar and cfg.lead_end>cfg.lead_start then
    local lead=track("Lead focus · excerpt of guitar estimate")
    audio(lead,"guitar.wav",cfg.lead_start,cfg.lead_end,0.24)
    eq(lead,400,2450,cfg.lead_presence,5100,0.55)
    r.SetMediaTrackInfo_Value(lead,"D_VOL",amp(cfg.lead_db))
    r.SetMediaTrackInfo_Value(lead,"D_WIDTH",0.78)
    send(lead,delay,-12)
    send(lead,haze,-19)
  end
  local state=assert(io.open(dir.."fx-state.tsv","w"))
  for j=-1,r.CountTracks(proj)-1 do
    local group=j==-1 and master or r.GetTrack(proj,j)
    local _,name=r.GetTrackName(group)
    for i=0,r.TrackFX_GetCount(group)-1 do
      local _,effect=r.TrackFX_GetFXName(group,i)
      for p=0,r.TrackFX_GetNumParams(group,i)-1 do
        local _,parameter=r.TrackFX_GetParamName(group,i,p)
        local _,value=r.TrackFX_GetFormattedParamValue(group,i,p)
        state:write(name,"\t",effect,"\t",parameter,"\t",value,"\n")
      end
    end
    for i=0,r.GetTrackNumSends(group,0)-1 do
      local _,target=r.GetTrackSendName(group,i,"")
      state:write(name,"\tSend\t",target,"\t",r.GetTrackSendInfo_Value(group,0,i,"D_VOL"),"\n")
    end
  end
  state:close()
  r.SetEditCurPos(0,false,false)
  render_settings("METALLIC DREAM - Final Master",cfg.source_seconds+cfg.tail)
  r.Main_SaveProjectEx(proj,dir.."METALLIC DREAM.RPP",8)
  return r.GetAppVersion()
end

local ok,message=xpcall(build,debug.traceback)
local f=assert(io.open(dir.."host-status.tmp","w"))
f:write(ok and "BUILT\n" or "ERROR\n",message,"\n")
f:close()
assert(os.rename(dir.."host-status.tmp",dir.."host-status.txt"))
