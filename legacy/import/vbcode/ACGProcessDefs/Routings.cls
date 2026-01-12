VERSION 1.0 CLASS
BEGIN
  MultiUse = -1  'True
  Persistable = 0  'NotPersistable
  DataBindingBehavior = 0  'vbNone
  DataSourceBehavior  = 0  'vbNone
  MTSTransactionMode  = 0  'NotAnMTSObject
END
Attribute VB_Name = "Routings"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = True
'/*
' * Copyright 2004 Anite - Central Government Division
' *    http://www.anite.com/publicsector
' *
' * Licensed under the Apache License, Version 2.0 (the "License");
' * you may not use this file except in compliance with the License.
' * You may obtain a copy of the License at
' *
' *    http://www.apache.org/licenses/LICENSE-2.0
' *
' * Unless required by applicable law or agreed to in writing, software
' * distributed under the License is distributed on an "AS IS" BASIS,
' * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
' * See the License for the specific language governing permissions and
' * limitations under the License.
' */
Option Explicit
Private mCol As Collection
Private mParentContainer As Container
Private WithEvents mContainer As Container
Attribute mContainer.VB_VarHelpID = -1

Friend Property Set ParentContainer(v As Container)
    Set mParentContainer = v
End Property

Public Property Get ProcessDef() As ProcessDef
    Set ProcessDef = mParentContainer.GetParent
End Property

Private Sub Class_Initialize()
    Set mCol = New Collection
    Set mContainer = New Container
End Sub

Public Function Add(oTaskOrg As TaskDef, oTaskDest As TaskDef, Optional GUID As String = vbNullString) As RoutingDef
    Dim oNew As RoutingDef
    
    Set oNew = New RoutingDef
    Set oNew.ParentContainer = mContainer
    
    If Len(GUID) = 0 Then
        oNew.GUID = CreateGUID
    Else
        oNew.GUID = GUID
    End If
    
    Set oNew.TaskOrg = oTaskOrg
    Set oNew.TaskDest = oTaskDest
    
    mCol.Add oNew, oNew.GUID
    
    oTaskOrg.RoutingOut.Add oNew
    oTaskDest.RoutingIn.Add oNew
    
    Set Add = oNew
End Function

Public Property Get Item(vntIndexKey As Variant) As RoutingDef
Attribute Item.VB_UserMemId = 0
    Set Item = mCol(vntIndexKey)
End Property

Public Property Get Count() As Long
    Count = mCol.Count
End Property

Public Sub Remove(vntIndexKey As Variant)
    Dim oRemove As RoutingDef
    Set oRemove = mCol(vntIndexKey)
    oRemove.TaskDest.RoutingIn.Remove oRemove.GUID
    oRemove.TaskOrg.RoutingOut.Remove oRemove.GUID
    mCol.Remove oRemove.GUID
End Sub

Public Property Get NewEnum() As IUnknown
Attribute NewEnum.VB_UserMemId = -4
Attribute NewEnum.VB_MemberFlags = "40"
    Set NewEnum = mCol.[_NewEnum]
End Property


Private Sub mContainer_GetMe(oReturn As Object)
    Set oReturn = Me
End Sub

Friend Sub ChangeGUID(oRoutingDef As RoutingDef, OldGUID As String)
    mCol.Remove OldGUID
    mCol.Add oRoutingDef, oRoutingDef.GUID
    oRoutingDef.TaskOrg.RoutingOut.Remove OldGUID
    oRoutingDef.TaskOrg.RoutingOut.Add oRoutingDef
    oRoutingDef.TaskDest.RoutingIn.Remove OldGUID
    oRoutingDef.TaskDest.RoutingIn.Add oRoutingDef
End Sub
